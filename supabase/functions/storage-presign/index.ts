// Annotie — Faz 5: R2 presigned URL üreten Edge Function
//
// İstemci R2 kimlik bilgilerini ASLA görmez. Bu fonksiyon:
//   1. Kullanıcının Supabase JWT'sini doğrular (verify_jwt = true varsayılan).
//   2. RLS ile dataset/görsel erişimini kontrol eder (kullanıcının oturumuyla).
//   3. R2 için kısa ömürlü presigned PUT/GET URL üretir (aws4fetch).
//
// Gerekli secret'lar (Supabase > Edge Functions > Secrets):
//   R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
// (SUPABASE_URL ve SUPABASE_ANON_KEY otomatik sağlanır.)

import { AwsClient } from "https://esm.sh/aws4fetch@1.0.20";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const EXPIRES = 600; // saniye
const WRITE_ROLES = ["owner", "admin", "annotator"];

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
  if (!contentHash || (op !== "put" && op !== "get")) {
    return json({ error: "content_hash ve op (put|get) gerekli" }, 400);
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

  // --- Yetkilendirme ---
  if (op === "put") {
    if (!datasetId) return json({ error: "dataset_id gerekli (put)" }, 400);
    // Dataset görünür mü (üye mi) + yazma rolü var mı?
    const { data: ds } = await supabase
      .from("datasets").select("team_id").eq("id", datasetId).single();
    if (!ds) return json({ error: "Dataset bulunamadı veya erişim yok" }, 403);
    const { data: mem } = await supabase
      .from("memberships").select("role")
      .eq("team_id", ds.team_id).eq("user_id", user.id).single();
    if (!mem || !WRITE_ROLES.includes(mem.role)) {
      return json({ error: "Yazma yetkiniz yok" }, 403);
    }
  } else {
    // GET: bu hash'e sahip ve kullanıcının erişebildiği bir görsel olmalı (RLS)
    const { data: img } = await supabase
      .from("images").select("id").eq("content_hash", contentHash).limit(1);
    if (!img || img.length === 0) {
      return json({ error: "Görsele erişim yok" }, 403);
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

  const key = `blobs/${contentHash}`; // içerik-adresli (dedup)
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
