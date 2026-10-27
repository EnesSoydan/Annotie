// Annotie — Faz 5: R2 presigned URL üreten Edge Function
//
// İstemci R2 kimlik bilgilerini ASLA görmez. Bu fonksiyon:
//   1. Kullanıcının Supabase JWT'sini doğrular (verify_jwt = true varsayılan).
//   2. RLS ile dataset/görsel erişimini kontrol eder (kullanıcının oturumuyla).
//   3. R2 için kısa ömürlü presigned PUT/GET URL üretir (aws4fetch).
//
// Görsel anahtarları ekip kapsamlıdır: teams/<team_id>/blobs/<hash>. Global
// blobs/<hash> önekine yalnızca 0008 öncesi yüklemeler için ve o ekibin
// legacy_blob_grants kaydı varsa okuma imzası verilir. Böylece hash'i bilen
// başka bir ekip, kendi datasetine sahte satır ekleyerek bir blob'u okuyamaz
// veya üzerine yazamaz. Anahtar asla istemcinin yazdığı storage_key'den gelmez.
//
// Gerekli secret'lar (Supabase > Edge Functions > Secrets):
//   R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
// (SUPABASE_URL ve SUPABASE_ANON_KEY otomatik sağlanır.)

import { AwsClient } from "https://esm.sh/aws4fetch@1.0.20";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const EXPIRES = 600; // saniye
const WRITE_ROLES = ["owner", "admin", "annotator"];
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok");
  if (req.method !== "POST") return json({ error: "POST gerekli" }, 405);

  // --- Girdi ---
  let body: any;
  try {
    body = await req.json();
  } catch {
    return json({ error: "Geçersiz JSON" }, 400);
  }
  const datasetId: string = body.dataset_id;
  const contentHash: string = body.content_hash;
  const op: string = body.op; // "put" | "get"
  const kind: string = body.kind ?? "image"; // "image" | "model"
  if (!contentHash || (op !== "put" && op !== "get")) {
    return json({ error: "content_hash ve op (put|get) gerekli" }, 400);
  }
  if (kind !== "image" && kind !== "model") {
    return json({ error: "kind (image|model) geçersiz" }, 400);
  }
  if (!/^[0-9a-f]{64}$/.test(contentHash)) {
    return json({ error: "content_hash sha256 hex olmalı" }, 400);
  }

  // --- Kullanıcı oturumu (RLS bu oturumla uygulanır) ---
  const authHeader = req.headers.get("Authorization");
  if (!authHeader) return json({ error: "Yetkisiz" }, 401);

  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_ANON_KEY")!,
    { global: { headers: { Authorization: authHeader } } },
  );

  const { data: userData, error: userErr } = await supabase.auth.getUser();
  const user = userData?.user;
  if (userErr || !user) return json({ error: "Yetkisiz" }, 401);

  // --- Yetkilendirme + anahtar ---
  let key: string;
  if (kind === "model") {
    // Kullanıcı modelleri: anahtar kullanıcının kendi önekinde. PUT her
    // oturumlu kullanıcıya açık (kendi önekine); GET için kullanıcının bu
    // hash'e sahip bir user_models satırı olmalı (RLS: owner_id = auth.uid()).
    if (op === "get") {
      const { data: mdl } = await supabase
        .from("user_models").select("id").eq("content_hash", contentHash).limit(1);
      if (!mdl || mdl.length === 0) {
        return json({ error: "Modele erişim yok" }, 403);
      }
    }
    key = `models/${user.id}/${contentHash}`;  // kullanıcıya özel
  } else {
    if (!datasetId || !UUID_RE.test(datasetId)) {
      return json({ error: "dataset_id (uuid) gerekli" }, 400);
    }
    // Dataset görünür mü (RLS: ekip üyesi mi)?
    const { data: ds } = await supabase
      .from("datasets").select("team_id").eq("id", datasetId).maybeSingle();
    if (!ds) return json({ error: "Dataset bulunamadı veya erişim yok" }, 403);
    const teamKey = `teams/${ds.team_id}/blobs/${contentHash}`;

    if (op === "put") {
      const { data: mem } = await supabase
        .from("memberships").select("role")
        .eq("team_id", ds.team_id).eq("user_id", user.id).maybeSingle();
      if (!mem || !WRITE_ROLES.includes(mem.role)) {
        return json({ error: "Yazma yetkiniz yok" }, 403);
      }
      key = teamKey;  // yeni yüklemeler her zaman ekip önekine
    } else {
      // GET: bu datasette bu hash'e sahip bir görsel olmalı (RLS: üyelik)
      const { data: img } = await supabase
        .from("images").select("id")
        .eq("dataset_id", datasetId).eq("content_hash", contentHash).limit(1);
      if (!img || img.length === 0) {
        return json({ error: "Görsele erişim yok" }, 403);
      }
      // 0008 öncesi yüklenen blob'lar global önekte kaldı; yalnızca migrasyon
      // anında bu ekibe ait olduğu kaydedilen hash'ler oradan okunur.
      const { data: legacy } = await supabase
        .from("legacy_blob_grants").select("content_hash")
        .eq("team_id", ds.team_id).eq("content_hash", contentHash).limit(1);
      key = legacy && legacy.length > 0 ? `blobs/${contentHash}` : teamKey;
    }
  }

  // --- R2 presigned URL ---
  const accountId = Deno.env.get("R2_ACCOUNT_ID");
  const accessKeyId = Deno.env.get("R2_ACCESS_KEY_ID");
  const secretAccessKey = Deno.env.get("R2_SECRET_ACCESS_KEY");
  const bucket = Deno.env.get("R2_BUCKET");
  if (!accountId || !accessKeyId || !secretAccessKey || !bucket) {
    return json({ error: "Sunucu deposu yapılandırılmamış (R2 secret eksik)" }, 500);
  }

  const endpoint = `https://${accountId}.r2.cloudflarestorage.com`;
  const url = new URL(`${endpoint}/${bucket}/${key}`);
  url.searchParams.set("X-Amz-Expires", String(EXPIRES));

  const aws = new AwsClient({
    accessKeyId,
    secretAccessKey,
    region: "auto",
    service: "s3",
  });

  const signed = await aws.sign(url.toString(), {
    method: op === "put" ? "PUT" : "GET",
    aws: { signQuery: true },
  });

  return json({ url: signed.url, key, expires_in: EXPIRES });
});
