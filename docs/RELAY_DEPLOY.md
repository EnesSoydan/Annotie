# Relay Sunucusunu Ubuntu'da Çalıştırma (Faz 7)

Canlı işbirliği relay'ini (`server/`) kendi Ubuntu sunucunda çalıştır; tüm
istemciler (farklı pencereler/bilgisayarlar) ona bağlanır. Her seferinde
yerelde başlatmana gerek kalmaz.

> Relay sadece **canlı senkron** yapar (kalıcı veri DB+R2'de). Hafıza-içidir;
> yeniden başlasa bile etiketler kaybolmaz (DB'de duruyor).

> **Kimlik doğrulama zorunludur.** Relay, `SUPABASE_URL` + `SUPABASE_ANON_KEY`
> verilmeden **başlamaz**. Kimlik doğrulamasız mod yalnızca güvenilir LAN/test
> için `RELAY_INSECURE_OPEN=1` ile bilerek açılır.

---

## 0. Ön koşul: 0008 migrasyonu

Relay, ekip odasına katılan kullanıcının rolünü Supabase'deki
`my_dataset_role` RPC'si ile öğrenir. Bu fonksiyon
[`0008_security_hardening.sql`](../supabase/migrations/0008_security_hardening.sql)
ile gelir; relay'i güncellemeden **önce** bu migrasyonu çalıştır (bkz.
[SUPABASE_KURULUM.md](SUPABASE_KURULUM.md)). Migrasyon yoksa tüm `join_room`
istekleri "erişim yetkiniz yok" hatasıyla reddedilir.

---

## 1. Kodu sunucuya kopyala

Windows'tan (proje kökünde PowerShell):

```powershell
scp -r server KULLANICI@SUNUCU_IP:~/annotie-relay-src
```

veya sunucuda git ile (repo erişimi varsa):

```bash
git clone <REPO_URL> ~/annotie && ln -s ~/annotie/server ~/annotie-relay-src
```

---

## 2. Yapılandırma (`server/.env`)

```bash
cd ~/annotie-relay-src
cp .env.example .env
nano .env
```

Doldurulacaklar:

| Değişken | Açıklama |
|---|---|
| `SUPABASE_URL` | `https://YOUR-PROJECT-REF.supabase.co` |
| `SUPABASE_ANON_KEY` | anon/publishable key (`sb_publishable_...`). **service_role asla.** |
| `RELAY_BIND_ADDR` | `127.0.0.1` (varsayılan, reverse proxy arkası) veya `0.0.0.0` (LAN'dan doğrudan erişim) |
| `RELAY_INSECURE_OPEN` | Yalnızca güvenilir LAN/test: `1` → kimlik doğrulamasız |
| `RELAY_MAX_MESSAGE_BYTES` | Tek mesaj sınırı (varsayılan 2 MiB) |
| `RELAY_RATE_PER_SEC` / `RELAY_RATE_BURST` | Bağlantı başına hız sınırı (varsayılan 50/sn, 200 ani) |

`.env` git'e ve Docker imajına girmez (`.gitignore`, `.dockerignore`).

---

## 3. Docker ile çalıştır (önerilen)

```bash
cd ~/annotie-relay-src
sudo docker compose up -d --build
sudo docker compose logs -f          # "Relay kimlik doğrulaması etkin (Supabase)."
curl http://127.0.0.1:8765/health    # {"status":"ok","auth":"supabase",...}
```

Diğer komutlar: `sudo docker compose restart`, `sudo docker compose down`.

Konteyner root olmayan bir kullanıcıyla çalışır ve `/health` üzerinden sağlık
kontrolü yapar (`docker ps` → `healthy`).

---

## 4. Erişim modu

### A) İnternete açık: TLS'li reverse proxy (önerilen)

`RELAY_BIND_ADDR=127.0.0.1` (varsayılan) bırak; relay yalnızca sunucunun
kendisinden erişilebilir olur. Önüne [Caddy](https://caddyserver.com/) koy
(sertifikayı otomatik alır, WebSocket'i otomatik geçirir).
`/etc/caddy/Caddyfile`:

```
relay.alanadi.com {
    reverse_proxy 127.0.0.1:8765
}
```

```bash
sudo systemctl reload caddy
sudo ufw allow 443/tcp
```

İstemcide `collab_url`: `wss://relay.alanadi.com/ws`.

### B) Yalnızca yerel ağ (LAN)

`.env` içinde `RELAY_BIND_ADDR=0.0.0.0` ayarla, `docker compose up -d` ile
yeniden başlat ve portu yalnızca ağına aç:

```bash
sudo ufw allow from 192.168.1.0/24 to any port 8765 proto tcp
```

İstemcide `collab_url`: `ws://SUNUCU_IP:8765/ws`. Bu modda token'lar ağ
üzerinde şifresiz gider; yalnızca güvendiğin ağda kullan.

---

## 5. Alternatif: venv + systemd (Docker'sız)

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip
cd ~/annotie-relay-src
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

`/etc/systemd/system/annotie-relay.service`:

```ini
[Unit]
Description=Annotie Collab Relay
After=network.target

[Service]
User=UBUNTU_KULLANICI
WorkingDirectory=/home/UBUNTU_KULLANICI/annotie-relay-src
EnvironmentFile=/home/UBUNTU_KULLANICI/annotie-relay-src/.env
# Yalnızca reverse proxy arkasında: 127.0.0.1; LAN için 0.0.0.0
Environment=RELAY_HOST=127.0.0.1
ExecStart=/home/UBUNTU_KULLANICI/annotie-relay-src/venv/bin/python main.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now annotie-relay
journalctl -u annotie-relay -f
```

> systemd modunda dinlenen adres `RELAY_HOST` ile seçilir;
> `RELAY_BIND_ADDR` yalnızca docker-compose'da kullanılır.

---

## 6. İstemciyi (uygulama) sunucuya yönlendir

Proje kökündeki `cloud_config.json` dosyasına `collab_url` ekle:

```json
{
  "url": "https://YOUR-PROJECT-REF.supabase.co",
  "anon_key": "sb_publishable_...",
  "collab_url": "wss://relay.alanadi.com/ws"
}
```

Alternatif: `COLLAB_URL` ortam değişkeni.

Uygulama her (yeniden) bağlantıda güncel Supabase oturum token'ını gönderir.
Ekip datasetleri ve kodla açılan manuel lobiler için **giriş yapmış olmak
gerekir** (açık modda hariç).

---

## 7. Doğrulama

- `curl http://127.0.0.1:8765/health` → `"auth": "supabase"`.
- İki hesap (aynı ekip) → aynı ekip datasetini aç → biri etiketler, diğerinde
  anında görünmeli; presence noktaları çıkmalı. Logda
  `Oda katılım: <dataset_id> (Ad, annotator)` görülür.
- Ekipte **viewer** olan bir hesap odaya katılır ve değişiklikleri görür, ama
  kendi düzenlemeleri diğerlerine gitmez ("düzenleme yetkiniz yok" hatası).
- Ekip üyesi olmayan bir hesap odaya katılamaz.

---

## Mevcut kurulumdan geçiş (açık moddan)

Eski `docker-compose.yml` kimlik doğrulamasız (açık) moddaydı. Yeni sürümü
`up -d --build` ile kurduğunda `.env` yoksa relay **başlamaz** (logda
"kimlik doğrulaması yapılandırılmamış"). Sırayla:

1. Supabase'de `0008_security_hardening.sql` çalıştır.
2. `server/.env` oluştur (`SUPABASE_URL`, `SUPABASE_ANON_KEY`; LAN'dan doğrudan
   bağlanılıyorsa `RELAY_BIND_ADDR=0.0.0.0`).
3. `sudo docker compose up -d --build`.
4. Tüm istemcileri yeni sürüme güncelle (eski istemciler manuel lobilerde token
   göndermez).

---

## Sorun giderme

| Belirti | Çözüm |
|--------|-------|
| Konteyner sürekli yeniden başlıyor, log: "yapılandırılmamış" | `.env` içinde `SUPABASE_URL` + `SUPABASE_ANON_KEY` yok |
| "Bu ekip datasetine erişim yetkiniz yok" | 0008 çalıştırılmamış, token süresi dolmuş veya kullanıcı ekip üyesi değil |
| "Lobi oluşturmak/katılmak için giriş yapmanız gerekiyor" | Uygulamada Hesap → Giriş Yap; ya da relay'i açık modda çalıştır |
| "düzenleme yetkiniz yok (izleyici)" | Kullanıcının ekip rolü viewer; owner/admin rolü değiştirmeli |
| LAN'dan bağlanılamıyor | `RELAY_BIND_ADDR=0.0.0.0` ve `ufw` kuralı |
| "Mesaj çok büyük" | Çok büyük manifest/polygon; `RELAY_MAX_MESSAGE_BYTES` artır |
