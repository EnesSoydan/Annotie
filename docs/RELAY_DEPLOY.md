# Relay Sunucusunu Ubuntu'da Çalıştırma (Faz 7)

Canlı işbirliği relay'ini (`server/`) kendi Ubuntu sunucunda çalıştır; tüm
istemciler (farklı pencereler/bilgisayarlar) ona bağlanır. Her seferinde
yerelde başlatmana gerek kalmaz.

> Relay sadece **canlı senkron** yapar (kalıcı veri DB+R2'de). Hafıza-içidir;
> yeniden başlasa bile etiketler kaybolmaz (DB'de duruyor).

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

## 2. Bağımlılıkları kur (sunucuda)

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip
cd ~/annotie-relay-src
python3 -m venv venv
source venv/bin/activate
pip install fastapi "uvicorn[standard]" websockets
```

Hızlı test:

```bash
cd ~/annotie-relay-src
python main.py        # 0.0.0.0:8765 dinler
# Başka terminalden:  curl http://127.0.0.1:8765/health  → {"status":"ok",...}
```

`Ctrl+C` ile durdur; kalıcı çalışması için 3. adıma geç.

---

## 3. Kalıcı servis (systemd) — önerilen

`/etc/systemd/system/annotie-relay.service` oluştur:

```ini
[Unit]
Description=Annotie Collab Relay
After=network.target

[Service]
User=UBUNTU_KULLANICI
WorkingDirectory=/home/UBUNTU_KULLANICI/annotie-relay-src
ExecStart=/home/UBUNTU_KULLANICI/annotie-relay-src/venv/bin/python main.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Etkinleştir:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now annotie-relay
sudo systemctl status annotie-relay      # active (running) olmalı
journalctl -u annotie-relay -f           # canlı log
```

---

## 4. Portu aç (firewall)

```bash
sudo ufw allow 8765/tcp
```

> Bulut sağlayıcıda (AWS/Hetzner/DO) ayrıca **güvenlik grubu / firewall**'dan
> 8765 TCP'yi açman gerekebilir.

---

## 5. İstemciyi (uygulama) sunucuya yönlendir

Windows'ta proje kökündeki `cloud_config.json` dosyasına `collab_url` ekle:

```json
{
  "url": "https://YOUR-PROJECT-REF.supabase.co",
  "anon_key": "sb_publishable_...",
  "collab_url": "ws://SUNUCU_IP:8765/ws"
}
```

Alternatif: `COLLAB_URL` ortam değişkeni.

Artık ekip dataseti açtığında uygulama otomatik bu relay'e bağlanır.

---

## 6. Doğrulama

- İki pencere/iki hesap (aynı ekip) → aynı ekip datasetini aç → biri etiketler,
  diğerinde anında görünmeli; presence noktaları çıkmalı.
- Sunucuda `journalctl -u annotie-relay -f` ile "Oda katılım" loglarını gör.

---

## Güvenlik notu (önemli)

Relay şu an **kimlik doğrulaması yapmıyor** — `room_id` (=dataset_id, UUID)
bilen herkes o odaya bağlanabilir. UUID tahmin edilmesi zordur ama:

- **Geçici/test için:** firewall'u yalnızca kendi IP'lerine aç (`ufw allow from SENIN_IP to any port 8765`).
- **Üretim için (sonraki adım):** relay'e Supabase JWT doğrulaması + ekip üyeliği
  kontrolü eklenmeli (Faz 7.2). Ayrıca nginx + TLS ile `wss://` önerilir.

## (Opsiyonel) TLS / wss

nginx reverse proxy ile `wss://alanadi/ws` → `127.0.0.1:8765`. Sertifika için
certbot. Bu durumda `collab_url`: `wss://alanadi/ws`.
