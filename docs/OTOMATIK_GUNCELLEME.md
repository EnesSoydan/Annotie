# Annotie otomatik güncelleme

Annotie'nin paketlenmiş Windows sürümü, açılıştan kısa süre sonra GitHub
Releases API'sini kontrol eder. Daha yeni bir release ve Windows ZIP'i varsa
kullanıcıya güncelleme sorar. İndirme tamamlandıktan sonra ayrı
`AnnotieUpdater.exe` uygulamayı kapatır, ZIP'i güvenli biçimde açar ve
kurulum klasöründeki dosyaları yenileriyle değiştirir.

Kullanıcı verileri korunur:

- `%USERPROFILE%\.annotie` klasörüne dokunulmaz.
- Mevcut `cloud_config.json` güncelleme sırasında korunur.
- Güncelleme yalnızca uygulamanın kurulum klasörünü değiştirir.

## Windows release hazırlama

`build_exe.bat` çalıştırıldığında şunlar üretilir:

- `dist\Annotie\Annotie.exe`
- `dist\Annotie\AnnotieUpdater.exe`

Release ZIP'inin içinde iki dosya da bulunmalıdır. Örneğin PowerShell'de:

```powershell
Compress-Archive -Path .\dist\Annotie -DestinationPath .\dist\Annotie-Windows.zip -Force
```

Sonra GitHub Releases'te yeni sürüm oluşturup bu ZIP'i asset olarak yükleyin.
Tag sürüm numarası `v1.4.2` biçiminde olmalıdır. Yeni bir sürüm çıkarırken
`src/utils/constants.py` içindeki `APP_VERSION` değerini de aynı sürüme yükseltin.

Güncelleme sistemi GitHub'daki `EnesSoydan/Annotie` reposunun son release'ini
izler ve Windows ZIP adında `windows` geçen asset'i tercih eder.
