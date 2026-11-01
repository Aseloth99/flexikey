"""FlexiKey çoklu dil (TR / EN) yerelleştirme modülü."""

from __future__ import annotations

import locale
import os
import sys
from typing import Any

LOCALES: dict[str, dict[str, str]] = {
    "tr": {
        "app_title": "FlexiKey",
        "ready": "FlexiKey Hazır",
        "tab_hotkeys": "Klavye Kısayolları",
        "tab_expansions": "Metin Genişletme",
        "menu_app": "Uygulama",
        "menu_view": "Görünüm",
        "view": "Görünüm",
        "menu_settings": "Ayarlar",
        "new_hotkey": "Yeni Kısayol",
        "new_expansion": "Yeni Genişletme",
        "refresh_list": "Listeyi Yenile",
        "exit": "Çıkış",
        "settings": "Ayarlar",
        "change_theme": "Temayı Değiştir",
        "export_settings": "Ayarları Dışa Aktar…",
        "import_settings": "Ayarları İçe Aktar…",
        "user_guide": "Kullanım Kılavuzu",
        "about": "FlexiKey Hakkında",
        "about_version": "Sürüm {}",
        "settings_title": "Ayarlar",
        "appearance": "Görünüm",
        "theme": "Tema",
        "theme_system": "Sistem",
        "theme_light": "Açık",
        "theme_dark": "Koyu",
        "accent_color": "Renk",
        "accent_blue": "Mavi (Varsayılan)",
        "accent_indigo": "İndigo",
        "accent_purple": "Mor",
        "accent_rose": "Gül",
        "accent_emerald": "Zümrüt",
        "accent_cyan": "Turkuaz",
        "accent_amber": "Kehribar",
        "accent_crimson": "Kırmızı",
        "language": "Dil",
        "lang_auto": "Otomatik (Sistem)",
        "lang_tr": "Türkçe",
        "lang_en": "English",
        "behavior": "Davranış",
        "start_minimized": "Sistem Tepsisinde Simge Durumunda Başlat",
        "start_at_login": "Açılışta Başlat",
        "start_at_login_tip": "Oturum açtığınızda FlexiKey kendiliğinden başlar",
        "show_notifications": "Masaüstü Bildirimlerini Göster",
        "show_notifications_tip": "Kısayol veya eylem tetiklendiğinde masaüstü bildirimi gösterilir",
        "updates": "Güncellemeler",
        "auto_update_check": "Güncellemeleri Otomatik Kontrol Et",
        "auto_update_tip": "Yeni sürüm bulunduğunda arka planda indirilir ve uygulama kullanılmıyorken kurulur.",
        "check_updates": "Kontrol Et",
        "update_pill": "Güncelle · v{version}",
        "update_pill_tip": "Yeni sürüm v{version} hazır; ayrıntılar ve kurulum için tıklayın",
        "update_new_version": "Yeni sürüm: v{version}",
        "auto_update_install": "Güncellemeleri Otomatik Kur",
        "update_auto_failed": "Otomatik güncelleme tamamlanamadı; başlık çubuğundaki Güncelle düğmesinden yeniden deneyebilirsiniz.",
        "checking_updates": "Güncelleme kontrol ediliyor…",
        "update_available": "Yeni sürüm mevcut",
        "up_to_date": "Güncel · v{}",
        "update_check_failed": "Güncelleme kontrol edilemedi",
        "backup_restore": "Yedekleme ve Aktarım",
        "save": "Kaydet",
        "cancel": "İptal",
        "settings_saved": "Ayarlar başarıyla kaydedildi.",
        "info": "Bilgi",
        "tray_show": "Göster",
        "tray_hide": "Gizle",
        "tray_exit": "Çıkış",
        "col_active": "Aktif",
        "col_shortcut": "Kısayol",
        "col_action_type": "İşlem Türü",
        "col_action_content": "İşlem / İçerik",
        "col_description": "Açıklama",
        "col_keyword": "Kısaltma",
        "col_expanded_text": "Genişletilmiş Metin",
        "btn_add_hotkey": "Yeni Kısayol Ekle",
        "btn_add_expansion": "Yeni Genişletme Ekle",
        "btn_edit": "✏️ Düzenle",
        "btn_delete": "🗑️ Sil",
        "search_placeholder": "Ara…",
        "search_command": "Komut ara…",
        "btn_toggle": "⚡ Aktif/Pasif",
        "btn_refresh": "🔄 Yenile",
        "btn_short_add": "Kısayol Ekle",
        "btn_exp_add": "Genişletme Ekle",
        "empty_hotkeys": "Henüz kısayol eklenmedi. Bir tuş kombinasyonuna eylem atamak için aşağıdaki düğmeyi kullanın.",
        "state_active": "Aktif",
        "state_passive": "Pasif",
        "summary_hotkeys": "{n} kısayol · {a} aktif",
        "summary_expansions": "{n} genişletme · {a} aktif",
        "empty_expansions": "Henüz genişletme eklenmedi. Kısa bir tetikleyiciyi uzun bir metne dönüştürmek için aşağıdaki düğmeyi kullanın.",
        "chip_expansion": "Genişletme",
        "chip_rich_expansion": "Zengin Metin Genişletme",
        "tray_quick_actions": "Hızlı İşlemler",
        "tray_disable_all": "Tüm Kısayolları Devre Dışı Bırak",
        "tray_reload_config": "Yapılandırmayı Yeniden Yükle",
        "tray_hotkeys_disabled": "Kısayollar Devre Dışı",
        "tray_hotkeys_disabled_msg": "Tüm kısayollar geçici olarak devre dışı bırakıldı.",
        "tray_config_updated": "Yapılandırma Güncellendi",
        "tray_config_updated_msg": "Tüm ayarlar ve kısayollar başarıyla yüklendi.",
        "notif_success": "FlexiKey - Başarılı",
        "notif_warning": "FlexiKey - Uyarı",
        "notif_error": "FlexiKey - Hata",
        "backup_hint": "Kısayol ve metin genişletmelerinizi yedekleyin veya başka bir bilgisayardan içe aktarın.",
        "export_settings_btn": "Ayarları Dışa Aktar",
        "import_settings_btn": "Ayarları İçe Aktar",
        "close": "Kapat",
        "minimize": "Simge Durumuna Küçült",
        "maximize": "Ekranı Kapla / Geri Yükle",
        "ie_export_title": "Ayarları Dışa Aktar",
        "ie_import_title": "Ayarları İçe Aktar",
        "ie_export_header": "Dışa aktarılacak kategorileri seçin:",
        "ie_import_header": "İçe aktarılacak kategorileri seçin:",
        "ie_select_all": "Tüm Kategorileri Seç",
        "ie_cat_hotkeys": "Klavye Kısayolları",
        "ie_cat_expansions": "Metin Genişletmeleri",
        "ie_cat_theme": "Tema ve Vurgu Rengi Tercihleri",
        "ie_cat_behavior": "Davranış Ayarları (Başlangıç, Bildirimler)",
        "ie_cat_update": "Güncelleme Ayarları",
        "continue": "Devam Et",
        "error": "Hata",
        "yes": "Evet",
        "no": "Hayır",
        "startup_error": "Başlangıç ayarı değiştirilemedi:\n{}",
        "updater_not_found": "Güncelleme kontrolcüsü bulunamadı!",
        "exit_title": "Çıkış",
        "exit_confirm": "FlexiKey'den çıkmak istediğinizden emin misiniz?",
        "exit_warning": "Tüm kısayollar devre dışı kalacak.",
        "running_in_tray": "FlexiKey sistem tepsisinde çalışıyor",
        "action_text": "📝 Metin Yaz",
        "action_command": "⚙️ Sistem Komutu",
        "action_open_url": "🌐 Web Sitesi Aç",
        "action_open_file": "📁 Dosya/Klasör Aç",
        "action_run_program": "🚀 Program Çalıştır",
        "action_shortcut": "⌨️ Klavye Kısayolu Gönder",
        "cat_hotkeys": "Klavye Kısayolları",
        "cat_expansions": "Metin Genişletmeleri",
        "cat_theme": "Tema ve Vurgu Rengi",
        "cat_behavior": "Davranış Ayarları",
        "cat_update": "Güncelleme Ayarları",
        "hotkey_edit_title": "Kısayolu Düzenle",
        "hotkey_new_title": "Yeni Kısayol Ekle",
        "hotkey_label": "Kısayol",
        "hotkey_hint": "Alana tıklayıp hedef tuş kombinasyonuna basın (örn: Ctrl+Shift+M)",
        "action_type_label": "İşlem Türü",
        "action_type_hint": "Kısayol tetiklendiğinde yürütülecek eylemi seçin",
        "params_label": "İşlem Parametreleri",
        "rich_text_html": "Zengin Metin Biçimlendirmesi (HTML)",
        "enable_hotkey": "Bu Kısayolu Etkinleştir",
        "text_placeholder": "Otomatik yazılacak metni girin…",
        "html_placeholder": "Kalın, italik, altı çizili ve renkli metin desteklenir…",
        "select_file": "Dosya Seç",
        "all_files": "Tüm Dosyalar (*.*)",
        "expansion_edit_title": "Genişletmeyi Düzenle",
        "expansion_new_title": "Yeni Metin Genişletme",
        "trigger_example": "örn: @mail, /adres",
        "trigger_placeholder": "Tetikleyici kelime veya kısaltma…",
        "trigger_label": "Tetikleyici",
        "expanded_label": "Genişletilecek Metin",
        "paste_plain": "Biçimsiz Yapıştır",
        "paste_plain_tip": "Ctrl+Shift+V ile biçimsiz yapıştır",
        "expansion_placeholder": "Tetiklendiğinde yerine yazılacak metin…",
        "enable_expansion": "Bu Genişletmeyi Etkinleştir",
        "update_available_title": "Güncelleme Mevcut",
        "update_version_heading": "FlexiKey Sürüm {} Mevcut!",
        "update_version_line": "Mevcut sürüm: {} → Yeni sürüm: {}",
        "update_notes": "Sürüm Notları",
        "update_available_plain": "Güncelleme mevcut.",
        "update_later": "Daha Sonra",
        "update_now": "Şimdi Güncelle",
        "update_downloading": "İndiriliyor…",
        "update_downloaded_bytes": "{} indirildi",
        "update_download_done": "İndirme tamamlandı!",
        "update_installing": "Kuruluyor, lütfen bekleyin…",
        "update_restarting": "Kurulum tamamlandı! Uygulama yeniden başlatılıyor…",
        "tray_update_now": "Güncelle · v{version}",
        "update_size_line": "İndirme boyutu: {size}",
        "update_failed_inline": "Güncelleme tamamlanamadı: {error}",
        "update_retry": "Tekrar Dene",
        "update_installed_toast": "{app} v{version} sürümüne güncellendi.",
        "update_source_run": "Kaynak koddan çalışırken otomatik kurulum desteklenmez; yeni sürümü elle indirip kurun.",
        "update_err_missing": "Güncelleme dosyası bulunamadı.",
        "update_err_unexpected": "Beklenmeyen hata: {detail}",
        "update_err_insecure_url": "Güvenli olmayan indirme adresi: {detail}",
        "update_err_server_checksum": "Sunucunun gönderdiği sağlama toplamı geçersiz; güncelleme reddedildi.",
        "update_err_checksum_download": "Dosya bütünlüğü doğrulanamadı (sağlama toplamı uyuşmuyor).",
        "update_err_checksum_install": "Güncelleme dosyası doğrulanamadı (sağlama toplamı); kurulum iptal edildi.",
        "update_err_http": "Sunucu hata döndürdü (HTTP {code}).",
        "update_err_network": "Sunucuya bağlanılamadı: {detail}",
        "update_err_timeout": "Sunucu zamanında yanıt vermedi.",
        "update_err_io": "Dosya yazılamadı: {detail}",
        "update_err_read": "İndirilen paket okunamadı: {detail}",
        "update_err_not_package": "İndirilen dosya bir exe ya da zip değil.",
        "update_err_too_big": "Paket izin verilen boyuttan büyük.",
        "update_err_no_exe": "Güncelleme paketinde FlexiKey.exe yok.",
        "update_err_bad_zip": "Güncelleme paketi (zip) bozuk: {detail}",
        "update_err_write": "Yeni sürüm uygulamanın klasörüne yazılamadı: {detail}",
        "update_err_not_pe": "Paketteki dosya geçerli bir uygulama dosyası değil.",
        "update_err_arch": "Paket başka bir işlemci mimarisi için hazırlanmış.",
        "update_err_not_writable": "Uygulamanın bulunduğu klasöre yazılamıyor ({folder}). FlexiKey'i yazılabilir bir klasöre (örneğin Masaüstü ya da Belgeler) taşıyıp yeniden deneyin.",
        "update_err_swap": "Çalışan uygulama dosyası değiştirilemedi: {detail}",
        "update_err_swap2": "Yeni sürüm yerine konamadı: {detail}",
        "update_err_spawn": "Yeni sürüm başlatılamadı: {detail}",
        "update_check_title": "Güncelleme Kontrolü",
        "update_current": "FlexiKey güncel.\n\nMevcut sürüm: {}",
        "invalid_input": "Geçersiz Giriş",
        "fill_all_fields": "Lütfen tüm alanları doldurun.",
        "shortcut_required": "Lütfen bir kısayol tuşu belirleyin.",
        "no_selection": "Seçim Yok",
        "select_to_edit": "Düzenlemek için bir öğe seçin.",
        "select_to_delete": "Silmek için bir öğe seçin.",
        "select_to_toggle": "Aktif/pasif yapmak için bir öğe seçin.",
        "confirm_delete": "Silmeyi Onayla",
        "confirm_delete_hotkey": "Bu kısayolu silmek istediğinizden emin misiniz?",
        "confirm_delete_expansion": "Bu genişletmeyi silmek istediğinizden emin misiniz?",
        "hotkey_added": "Kısayol '{}' başarıyla eklendi.",
        "hotkey_updated": "Kısayol '{}' başarıyla güncellendi.",
        "hotkey_deleted": "Kısayol '{}' silindi.",
        "hotkey_enabled": "Kısayol '{}' aktif edildi.",
        "hotkey_disabled": "Kısayol '{}' pasif edildi.",
        "expansion_added": "Genişletme '{}' başarıyla eklendi.",
        "expansion_updated": "Genişletme '{}' başarıyla güncellendi.",
        "expansion_deleted": "Genişletme '{}' silindi.",
        "expansion_enabled": "Genişletme '{}' aktif edildi.",
        "expansion_disabled": "Genişletme '{}' pasif edildi.",
        "settings_reloaded": "Ayarlar başarıyla yeniden yüklendi!",
        "warning": "Uyarı",
        "select_category": "Lütfen en az bir ayar kategorisi seçin!",
        "json_files": "JSON Dosyaları (*.json);;Tüm Dosyalar (*.*)",
        "export_success": "Ayarlar başarıyla dışa aktarıldı.",
        "import_success": "Ayarlar başarıyla içe aktarıldı.",
        "import_confirm_title": "İçe Aktarma Onayı",
        "import_confirm": "Devam etmek istiyor musunuz?",
        "invalid_json": "Geçersiz JSON dosyası!",
        "export_error": "Ayarlar dışa aktarılırken hata oluştu",
        "import_error": "Ayarlar içe aktarılırken hata oluştu",
        "window_subtitle": "Gelişmiş Klavye Yöneticisi",
        "notif_written": "Yazıldı: {}",
        "notif_executed": "Çalıştırıldı: {}",
        "notif_sent": "Gönderildi: {}",
        "notif_url_empty": "URL boş!",
        "notif_opened": "Açıldı: {}",
        "notif_url_failed": "URL açılamadı: {}",
        "notif_error_prefix": "Hata: {}",
        "export_done_detail": "Seçilen ayarlar başarıyla dışa aktarıldı.\n\nAktarılan kategoriler:\n{}\n\nDosya: {}",
        "import_done_detail": "Seçilen ayarlar başarıyla içe aktarıldı.\n\nAktarılan kategoriler:\n{}\n\nTüm kısayollar ve metin genişletmeleri güncellendi.",
        "import_confirm_detail": "Seçilen ayar kategorileri mevcut ayarların üzerine yazılacak:\n\n{}\n\nDevam etmek istiyor musunuz?",
        "invalid_json_detail": "Geçersiz JSON dosyası! Lütfen geçerli bir FlexiKey ayar dosyası seçin.",
        "export_filename": "FlexiKey_Ayarlar_{}.json",
        "browse": "Gözat…",
        "select_folder": "Klasör Seç",
        "hint_shortcut_key": "Alana tıklayıp hedef tuş kombinasyonuna basın (örn: Ctrl+Shift+M)",
        "hint_action_type": "Kısayol tetiklendiğinde yürütülecek eylemi seçin",
        "hint_system_cmd": "Yürütmek istediğiniz sistem komutunu listeden belirleyin",
        "hint_url": "Açılacak web adresini girin (örn: https://www.google.com)",
        "hint_file": "Açılacak dosya veya klasörün yolunu belirtin",
        "hint_program": "Çalıştırılacak uygulamanın adı veya dosya yolu",
        "key_capture_placeholder": "Kısayol tuşuna veya kombinasyona basın…",
        "example_url": "https://www.ornek.com",
        "example_file": "C:\\Yol\\Dosya.txt",
        "example_program": "notepad.exe veya C:\\Program.exe",
        "hint_key_sequence": "Gönderilecek klavye kombinasyonunu girin",
        "hint_trigger": "Tetikleyiciyi yazdıktan sonra Boşluk (Space) tuşuna basmanız yeterlidir.",
        "tip_paste_plain": "Panodan biçimsiz metin yapıştır (HTML/biçim kodları olmadan)\nKısayol: Ctrl+Shift+V",
        "tip_expansion_text": "Düz metin veya HTML desteklenir.\nCtrl+Shift+V ile biçimsiz, Ctrl+V ile biçimli yapıştırabilirsiniz.",
        "placeholder_rich_text": "HTML kullanabilirsiniz:\n<b>Kalın</b>, <i>İtalik</i>, <u>Altı çizili</u>\n<font color='red'>Renkli metin</font>",
        "net_error_prefix": "Güncelleme kontrolü yapılamadı.\nLütfen internet bağlantınızı kontrol edin.",
        "check_error_prefix": "Güncelleme kontrolü sırasında bir hata oluştu:\n{}",
        "cmd_grp_power": "--- 🔋 Sistem Gücü ---",
        "cmd_shutdown": "Bilgisayarı Kapat",
        "cmd_restart": "Yeniden Başlat",
        "cmd_sleep": "Uyku Modu",
        "cmd_hibernate": "Hazırda Beklet",
        "cmd_lock": "Kilitle",
        "cmd_logout": "Oturumu Kapat",
        "cmd_turn_off_screen": "Ekranı Kapat",
        "cmd_empty_recycle_bin": "Geri Dönüşümü Boşalt",
        "cmd_grp_screen": "--- 📸 Ekran & Araçlar ---",
        "cmd_screenshot": "Ekran Görüntüsü",
        "cmd_snipping_tool": "Ekran Alıntısı Aracı",
        "cmd_clipboard_history": "Pano Geçmişi",
        "cmd_emoji_panel": "Emoji Paneli",
        "cmd_magnifier": "Büyüteç",
        "cmd_on_screen_keyboard": "Ekran Klavyesi",
        "cmd_grp_apps": "--- 📱 Uygulamalar & Araçlar ---",
        "cmd_task_mgr": "Görev Yöneticisi",
        "cmd_run_dialog": "Çalıştır Diyalogu",
        "cmd_cmd": "Komut İstemi",
        "cmd_powershell": "PowerShell",
        "cmd_explorer": "Dosya Gezgini",
        "cmd_notepad": "Not Defteri",
        "cmd_calc": "Hesap Makinesi",
        "cmd_paint": "Paint",
        "cmd_settings": "Ayarlar",
        "cmd_control_panel": "Denetim Masası",
        "cmd_device_manager": "Aygıt Yöneticisi",
        "cmd_volume_mixer": "Ses Karıştırıcısı",
        "cmd_services": "Hizmetler",
        "cmd_grp_media": "--- 🎵 Medya ---",
        "cmd_play_pause": "Oynat / Duraklat",
        "cmd_next_track": "Sonraki Şarkı",
        "cmd_prev_track": "Önceki Şarkı",
        "cmd_stop": "Durdur",
        "cmd_grp_volume": "--- 🔊 Ses ---",
        "cmd_volume_up": "Ses Aç",
        "cmd_volume_down": "Ses Kıs",
        "cmd_volume_mute": "Sesi Kapat",
        "cmd_volume_max": "Ses Maksimum",
        "cmd_volume_min": "Ses Minimum",
        "cmd_grp_windows": "--- 🪟 Pencere & Masaüstü ---",
        "cmd_show_desktop": "Masaüstünü Göster",
        "cmd_minimize_all": "Tüm Pencereleri Küçült",
        "cmd_task_view": "Görev Görünümü",
        "cmd_new_vdesktop": "Yeni Sanal Masaüstü",
        "cmd_next_vdesktop": "Sonraki Masaüstü",
        "cmd_prev_vdesktop": "Önceki Masaüstü",
        "cmd_close_vdesktop": "Sanal Masaüstünü Kapat",
        "cmd_snap_left": "Sola Yasla",
        "cmd_snap_right": "Sağa Yasla",
        "cmd_maximize_window": "Pencereyi Büyüt",
        "cmd_close_window": "Pencereyi Kapat",
        "cmd_switch_window": "Pencere Değiştir",
        "cmd_grp_browsers": "--- 🌐 Tarayıcılar ---",
        "cmd_chrome": "Chrome",
        "cmd_firefox": "Firefox",
        "cmd_edge": "Edge",
        "cmd_grp_browser_nav": "--- 🧭 Tarayıcı Gezintisi ---",
        "cmd_back": "Geri",
        "cmd_forward": "İleri",
        "cmd_refresh_page": "Sayfayı Yenile",
        "cmd_new_tab": "Yeni Sekme",
        "cmd_close_tab": "Sekmeyi Kapat",
        "cmd_reopen_tab": "Son Kapatılan Sekmeyi Aç",
        "cmd_grp_quick_access": "--- 📁 Hızlı Erişim ---",
        "cmd_this_pc": "Bu Bilgisayar",
        "cmd_downloads": "İndirilenler",
        "cmd_documents": "Belgelerim",
        "cmd_pictures": "Resimlerim",
        "cmd_music": "Müziklerim",
        "cmd_videos": "Videolarım",
        "cmd_desktop_folder": "Masaüstü Klasörü",
        "cmd_recycle_bin": "Geri Dönüşüm Kutusu",
        "cmd_grp_text": "--- ✏️ Metin & Düzenleme ---",
        "cmd_copy": "Kopyala",
        "cmd_cut": "Kes",
        "cmd_paste": "Yapıştır",
        "cmd_select_all": "Tümünü Seç",
        "cmd_undo": "Geri Al",
        "cmd_redo": "Yeniden Yap",
        "cmd_find": "Bul",
        "cmd_save": "Kaydet",
        "cmd_print": "Yazdır",
        "about_heading": "FlexiKey",
        "about_subtitle": "Gelişmiş Kısayol ve Metin Genişletme Yöneticisi",
        "about_description": "Küresel klavye kısayolları, zengin metin otomasyonu ve sistem entegrasyonları ile iş akışınızı hızlandırmak için geliştirilmiş profesyonel araç seti.",
        "about_copyright": "&copy; 2026 FlexiKey. Tüm hakları saklıdır.",
        "help_title": "Kullanım Kılavuzu",
        "help_heading": "FlexiKey Kullanım Kılavuzu",
        "help_section_hotkeys_title": "Klavye Kısayolu Tanımlama",
        "help_hotkeys_step1": "1. <b>Kısayol Ekle</b> butonuna tıklayın.",
        "help_hotkeys_step2": "2. Kısayol kutusuna tıklayıp hedef tuş kombinasyonuna basın (örn: Ctrl+Shift+M).",
        "help_hotkeys_step3": "3. Yürütülecek işlem türünü belirleyin ve gerekli parametreleri girin.",
        "help_hotkeys_step4": "4. <b>Kaydet</b> butonu ile kısayolu etkinleştirin.",
        "help_section_expansion_title": "Metin Genişletme",
        "help_expansion_step1": "1. <b>Genişletme Ekle</b> butonuna tıklayın.",
        "help_expansion_step2": "2. Tetikleyici bir kısaltma belirleyin (örn: <code>@mail</code>, <code>/adres</code>, <code>adres1</code>).",
        "help_expansion_step3": "3. Otomatik yerleştirilecek metni yazın (Zengin/HTML metin desteklenir).",
        "help_expansion_step4": "4. Herhangi bir uygulamada tetikleyiciyi yazıp ardından <b>Boşluk (Space)</b> tuşuna basmanız yeterlidir.",
        "help_section_shortcuts_title": "Uygulama Kısayolları",
        "help_sc_add_hotkey": "• <b>Ctrl+N:</b> Yeni Kısayol Ekle",
        "help_sc_add_expansion": "• <b>Ctrl+Shift+N:</b> Yeni Genişletme Ekle",
        "help_sc_toggle_theme": "• <b>Ctrl+T:</b> Temayı Değiştir (Açık / Koyu)",
        "help_sc_settings": "• <b>Ctrl+,:</b> Ayarlar Penceresi",
        "help_sc_refresh": "• <b>F5:</b> Listeyi Yenile",
        "help_sc_toggle": "• <b>Boşluk:</b> Seçili Ögeyi Aktif/Pasif Yap",
        "help_sc_guide": "• <b>F1:</b> Kullanım Kılavuzu",
        "help_sc_exit": "• <b>Ctrl+Q:</b> Uygulamadan Çıkış (Alt+F4 yalnızca pencereyi kapatır, uygulama tepside çalışır)",
        "import_preview_summary": "İçe aktarılacak: {} kısayol, {} genişletme.",
        "import_preview_skipped": "Geçersiz oldukları için {} kayıt atlanacak.",
        "import_preview_rejected": "Geçersiz değerler yoksayılacak: {}",
        "import_preview_risky": "⚠ {} eylem riskli (yıkıcı sistem komutu, program/dosya çalıştırma veya özel komut). Yalnızca güvendiğiniz bir kaynaktan gelen dosyaları içe aktarın.",
        "import_preview_list_header": "Kısayol eylemleri:",
        "import_preview_more": "… ve {} eylem daha (tamamı için “Ayrıntıları göster”)",
        "import_preview_update_url": "Güncelleme adresi şu olarak ayarlanacak: {}",
        "update_mandatory_installing": "Zorunlu güncelleme indirildi. FlexiKey kurulum için birkaç saniye içinde yeniden başlayacak.",
        "update_auto_installing": "Güncelleme indirildi. FlexiKey kurulum için birkaç saniye içinde yeniden başlayacak.",
        "confirm_destructive_title": "Onay Gerekli",
        "confirm_destructive_text": "“{}” eylemi çalıştırılacak. Devam etmek istiyor musunuz?",
        "confirm_destructive_power": "Bilgisayar veya oturum hemen kapanır/yeniden başlar; kaydedilmemiş çalışmalarınız kaybolabilir.",
        "confirm_destructive_recycle": "Geri dönüşüm kutusundaki tüm öğeler kalıcı olarak silinir.",
        "confirm_destructive_cancelled": "İptal edildi: {}",
        "settings_warn_title": "Ayar Dosyası Uyarısı",
        "settings_warn_corrupt_restored": "Ayar dosyası bozuktu; son yedekten geri yüklendi.\nBozuk dosya saklandı:\n{}",
        "settings_warn_corrupt_defaults": "Ayar dosyası bozuktu ve kullanılabilir yedek bulunamadı; varsayılan ayarlar kullanılıyor.\nBozuk dosya saklandı:\n{}",
        "settings_warn_invalid_records": "{} geçersiz kayıt atlandı. Özgün dosyanın bir kopyası şu adla saklandı: {}.invalid-*",
        "settings_warn_read_failed_backup": "Ayar dosyası okunamadı (başka bir program kullanıyor olabilir); yedekten okundu. Dosya değiştirilmedi:\n{}",
        "settings_warn_read_failed_defaults": "Ayar dosyası okunamadı (başka bir program kullanıyor olabilir); geçici olarak varsayılan ayarlar kullanılıyor. Dosya değiştirilmedi:\n{}",
        "cmd_not_installed": "Gerekli program bulunamadı: {}. Kurup tekrar deneyin.",
        "cmd_unsupported_platform": "Bu komut {} üzerinde desteklenmiyor: {}",
        "notif_url_no_browser": "Varsayılan bir tarayıcı bulunamadı",
        "input_status_title": "Klavye Kısayolları Kullanılamıyor",
        "input_status_wayland": "Wayland oturumu algılandı. Wayland, uygulamaların küresel klavye kısayollarını dinlemesine ve tuş göndermesine izin vermez; bu yüzden kısayollar ve metin genişletme çalışmayacak (program başlatma, URL açma gibi komutlar çalışır).\nÇözüm: oturum açarken 'X11 / Xorg' oturumunu seçin.",
        "input_status_no_display": "Grafik oturumuna (X11 DISPLAY) bağlanılamadı; küresel kısayollar ve metin genişletme devre dışı. FlexiKey'i masaüstü oturumunuzun içinden başlatın.",
        "input_status_macos_permission": "macOS izni gerekli: Sistem Ayarları → Gizlilik ve Güvenlik bölümünde FlexiKey için şu izinleri açın: {}.\nİzni verdikten sonra FlexiKey'e dönün; izin otomatik algılanır (algılanmazsa uygulamayı yeniden başlatın).",
        "input_status_missing_dependency": "Klavye bileşeni yüklenemedi ({}). Gerekli paketi kurun: pip install pynput",
        "input_perm_accessibility": "Erişilebilirlik",
        "input_perm_input_monitoring": "Girdi İzleme",
        "input_open_privacy_settings": "İzin Ayarlarını Aç",
    },
    "en": {
        "app_title": "FlexiKey",
        "ready": "FlexiKey Ready",
        "tab_hotkeys": "Keyboard Shortcuts",
        "tab_expansions": "Text Expansion",
        "menu_app": "App",
        "menu_view": "View",
        "view": "View",
        "menu_settings": "Settings",
        "new_hotkey": "New Shortcut",
        "new_expansion": "New Expansion",
        "refresh_list": "Refresh List",
        "exit": "Exit",
        "settings": "Settings",
        "change_theme": "Change Theme",
        "export_settings": "Export Settings…",
        "import_settings": "Import Settings…",
        "user_guide": "User Guide",
        "about": "About FlexiKey",
        "about_version": "Version {}",
        "settings_title": "Settings",
        "appearance": "Appearance",
        "theme": "Theme",
        "theme_system": "System",
        "theme_light": "Light",
        "theme_dark": "Dark",
        "accent_color": "Color",
        "accent_blue": "Blue (Default)",
        "accent_indigo": "Indigo",
        "accent_purple": "Purple",
        "accent_rose": "Rose",
        "accent_emerald": "Emerald",
        "accent_cyan": "Cyan",
        "accent_amber": "Amber",
        "accent_crimson": "Crimson",
        "language": "Language",
        "lang_auto": "Auto (System)",
        "lang_tr": "Türkçe",
        "lang_en": "English",
        "behavior": "Behavior",
        "start_minimized": "Start Minimized to System Tray",
        "start_at_login": "Start at Login",
        "start_at_login_tip": "FlexiKey starts automatically when you sign in",
        "show_notifications": "Show Desktop Notifications",
        "show_notifications_tip": "Show notification when shortcut or action is triggered",
        "updates": "Updates",
        "auto_update_check": "Check for Updates Automatically",
        "auto_update_tip": "When a new version is found, it is downloaded in the background and installed while the app is idle.",
        "check_updates": "Check for Updates",
        "update_pill": "Update · v{version}",
        "update_pill_tip": "Version v{version} is ready; click for details and installation",
        "update_new_version": "New version: v{version}",
        "auto_update_install": "Install Updates Automatically",
        "update_auto_failed": "The automatic update could not be completed; you can retry from the Update button in the title bar.",
        "checking_updates": "Checking for updates…",
        "update_available": "New version available",
        "up_to_date": "Up to date · v{}",
        "update_check_failed": "Could not check for updates",
        "backup_restore": "Backup & Export",
        "save": "Save",
        "cancel": "Cancel",
        "settings_saved": "Settings saved successfully.",
        "info": "Information",
        "tray_show": "Show",
        "tray_hide": "Hide",
        "tray_exit": "Exit",
        "col_active": "Active",
        "col_shortcut": "Shortcut",
        "col_action_type": "Action Type",
        "col_action_content": "Action / Content",
        "col_description": "Description",
        "col_keyword": "Keyword",
        "col_expanded_text": "Expanded Text",
        "btn_add_hotkey": "Add New Shortcut",
        "btn_add_expansion": "Add New Expansion",
        "btn_edit": "✏️ Edit",
        "btn_delete": "🗑️ Delete",
        "search_placeholder": "Search…",
        "search_command": "Search command…",
        "btn_toggle": "⚡ Toggle",
        "btn_refresh": "🔄 Refresh",
        "btn_short_add": "Add Shortcut",
        "btn_exp_add": "Add Expansion",
        "empty_hotkeys": "No shortcuts yet. Use the button below to assign an action to a key combination.",
        "state_active": "On",
        "state_passive": "Off",
        "summary_hotkeys": "{n} shortcuts · {a} active",
        "summary_expansions": "{n} expansions · {a} active",
        "empty_expansions": "No expansions yet. Use the button below to turn a short trigger into longer text.",
        "chip_expansion": "Expansion",
        "chip_rich_expansion": "Rich Text Expansion",
        "tray_quick_actions": "Quick Actions",
        "tray_disable_all": "Disable All Shortcuts",
        "tray_reload_config": "Reload Configuration",
        "tray_hotkeys_disabled": "Shortcuts Disabled",
        "tray_hotkeys_disabled_msg": "All shortcuts have been temporarily disabled.",
        "tray_config_updated": "Configuration Updated",
        "tray_config_updated_msg": "All settings and shortcuts loaded successfully.",
        "notif_success": "FlexiKey - Success",
        "notif_warning": "FlexiKey - Warning",
        "notif_error": "FlexiKey - Error",
        "backup_hint": "Back up your shortcuts and expansions, or import from another computer.",
        "export_settings_btn": "Export Settings",
        "import_settings_btn": "Import Settings",
        "close": "Close",
        "minimize": "Minimize to Tray",
        "maximize": "Maximize / Restore",
        "ie_export_title": "Export Settings",
        "ie_import_title": "Import Settings",
        "ie_export_header": "Select categories to export:",
        "ie_import_header": "Select categories to import:",
        "ie_select_all": "Select All Categories",
        "ie_cat_hotkeys": "Keyboard Shortcuts",
        "ie_cat_expansions": "Text Expansions",
        "ie_cat_theme": "Theme & Accent Preferences",
        "ie_cat_behavior": "Behavior Settings (Startup, Notifications)",
        "ie_cat_update": "Update Settings",
        "continue": "Continue",
        "error": "Error",
        "yes": "Yes",
        "no": "No",
        "startup_error": "Could not change startup setting:\n{}",
        "updater_not_found": "Update checker not found!",
        "exit_title": "Exit",
        "exit_confirm": "Are you sure you want to exit FlexiKey?",
        "exit_warning": "All shortcuts will be disabled.",
        "running_in_tray": "FlexiKey is running in the system tray",
        "action_text": "📝 Type Text",
        "action_command": "⚙️ System Command",
        "action_open_url": "🌐 Open Website",
        "action_open_file": "📁 Open File/Folder",
        "action_run_program": "🚀 Run Program",
        "action_shortcut": "⌨️ Send Keyboard Shortcut",
        "cat_hotkeys": "Keyboard Shortcuts",
        "cat_expansions": "Text Expansions",
        "cat_theme": "Theme & Accent",
        "cat_behavior": "Behavior Settings",
        "cat_update": "Update Settings",
        "hotkey_edit_title": "Edit Shortcut",
        "hotkey_new_title": "Add New Shortcut",
        "hotkey_label": "Shortcut",
        "hotkey_hint": "Click the field and press the target key combination (e.g. Ctrl+Shift+M)",
        "action_type_label": "Action Type",
        "action_type_hint": "Select the action to run when the shortcut is triggered",
        "params_label": "Action Parameters",
        "rich_text_html": "Rich Text Formatting (HTML)",
        "enable_hotkey": "Enable This Shortcut",
        "text_placeholder": "Enter text to type automatically…",
        "html_placeholder": "Bold, italic, underline and colored text supported…",
        "select_file": "Select File",
        "all_files": "All Files (*.*)",
        "expansion_edit_title": "Edit Expansion",
        "expansion_new_title": "New Text Expansion",
        "trigger_example": "e.g. @mail, /addr",
        "trigger_placeholder": "Trigger word or abbreviation…",
        "trigger_label": "Trigger",
        "expanded_label": "Expanded Text",
        "paste_plain": "Paste Plain Text",
        "paste_plain_tip": "Paste without formatting with Ctrl+Shift+V",
        "expansion_placeholder": "Text to insert when triggered…",
        "enable_expansion": "Enable This Expansion",
        "update_available_title": "Update Available",
        "update_version_heading": "FlexiKey Version {} Available!",
        "update_version_line": "Current version: {} → New version: {}",
        "update_notes": "Release Notes",
        "update_available_plain": "An update is available.",
        "update_later": "Later",
        "update_now": "Update Now",
        "update_downloading": "Downloading…",
        "update_downloaded_bytes": "{} downloaded",
        "update_download_done": "Download complete!",
        "update_installing": "Installing, please wait…",
        "update_restarting": "Installation complete! Restarting the app…",
        "tray_update_now": "Update · v{version}",
        "update_size_line": "Download size: {size}",
        "update_failed_inline": "The update could not be completed: {error}",
        "update_retry": "Try Again",
        "update_installed_toast": "{app} was updated to v{version}.",
        "update_source_run": "Automatic installation is not supported when running from source; download and install the new version manually.",
        "update_err_missing": "The update file was not found.",
        "update_err_unexpected": "Unexpected error: {detail}",
        "update_err_insecure_url": "Insecure download address: {detail}",
        "update_err_server_checksum": "The checksum sent by the server is invalid; the update was rejected.",
        "update_err_checksum_download": "The file integrity could not be verified (checksum mismatch).",
        "update_err_checksum_install": "The update file could not be verified (checksum); installation was cancelled.",
        "update_err_http": "The server returned an error (HTTP {code}).",
        "update_err_network": "Could not reach the server: {detail}",
        "update_err_timeout": "The server did not respond in time.",
        "update_err_io": "The file could not be written: {detail}",
        "update_err_read": "The downloaded package could not be read: {detail}",
        "update_err_not_package": "The downloaded file is neither an exe nor a zip.",
        "update_err_too_big": "The package is larger than allowed.",
        "update_err_no_exe": "The update package does not contain FlexiKey.exe.",
        "update_err_bad_zip": "The update package (zip) is corrupt: {detail}",
        "update_err_write": "The new version could not be written to the application folder: {detail}",
        "update_err_not_pe": "The file in the package is not a valid application file.",
        "update_err_arch": "The package was built for a different processor architecture.",
        "update_err_not_writable": "The application folder is not writable ({folder}). Move FlexiKey to a writable folder (for example Desktop or Documents) and try again.",
        "update_err_swap": "The running application file could not be replaced: {detail}",
        "update_err_swap2": "The new version could not be put in place: {detail}",
        "update_err_spawn": "The new version could not be started: {detail}",
        "update_check_title": "Update Check",
        "update_current": "FlexiKey is up to date.\n\nCurrent version: {}",
        "invalid_input": "Invalid Input",
        "fill_all_fields": "Please fill in all fields.",
        "shortcut_required": "Please specify a shortcut key.",
        "no_selection": "No Selection",
        "select_to_edit": "Select an item to edit.",
        "select_to_delete": "Select an item to delete.",
        "select_to_toggle": "Select an item to toggle.",
        "confirm_delete": "Confirm Delete",
        "confirm_delete_hotkey": "Are you sure you want to delete this shortcut?",
        "confirm_delete_expansion": "Are you sure you want to delete this expansion?",
        "hotkey_added": "Shortcut '{}' added successfully.",
        "hotkey_updated": "Shortcut '{}' updated successfully.",
        "hotkey_deleted": "Shortcut '{}' deleted.",
        "hotkey_enabled": "Shortcut '{}' enabled.",
        "hotkey_disabled": "Shortcut '{}' disabled.",
        "expansion_added": "Expansion '{}' added successfully.",
        "expansion_updated": "Expansion '{}' updated successfully.",
        "expansion_deleted": "Expansion '{}' deleted.",
        "expansion_enabled": "Expansion '{}' enabled.",
        "expansion_disabled": "Expansion '{}' disabled.",
        "settings_reloaded": "Settings reloaded successfully!",
        "warning": "Warning",
        "select_category": "Please select at least one settings category!",
        "json_files": "JSON Files (*.json);;All Files (*.*)",
        "export_success": "Settings exported successfully.",
        "import_success": "Settings imported successfully.",
        "import_confirm_title": "Confirm Import",
        "import_confirm": "Do you want to continue?",
        "invalid_json": "Invalid JSON file!",
        "export_error": "Error exporting settings",
        "import_error": "Error importing settings",
        "window_subtitle": "Advanced Keyboard Manager",
        "notif_written": "Typed: {}",
        "notif_executed": "Executed: {}",
        "notif_sent": "Sent: {}",
        "notif_url_empty": "URL is empty!",
        "notif_opened": "Opened: {}",
        "notif_url_failed": "Could not open URL: {}",
        "notif_error_prefix": "Error: {}",
        "export_done_detail": "Selected settings exported successfully.\n\nCategories:\n{}\n\nFile: {}",
        "import_done_detail": "Selected settings imported successfully.\n\nCategories:\n{}\n\nAll shortcuts and expansions updated.",
        "import_confirm_detail": "Selected categories will overwrite current settings:\n\n{}\n\nDo you want to continue?",
        "invalid_json_detail": "Invalid JSON file! Please select a valid FlexiKey settings file.",
        "export_filename": "FlexiKey_Settings_{}.json",
        "browse": "Browse…",
        "select_folder": "Select Folder",
        "hint_shortcut_key": "Click the field and press the target key combination (e.g. Ctrl+Shift+M)",
        "hint_action_type": "Select the action to run when the shortcut is triggered",
        "hint_system_cmd": "Select the system command to execute from the list",
        "hint_url": "Enter the web address to open (e.g. https://www.google.com)",
        "hint_file": "Specify the path to the file or folder to open",
        "hint_program": "Application name or file path to run",
        "key_capture_placeholder": "Press a key or key combination…",
        "example_url": "https://www.example.com",
        "example_file": "C:\\Path\\File.txt",
        "example_program": "notepad.exe or C:\\Program.exe",
        "hint_key_sequence": "Enter the keyboard combination to send",
        "hint_trigger": "After typing the trigger, simply press the Space key.",
        "tip_paste_plain": "Paste plain text from clipboard without HTML or formatting\nShortcut: Ctrl+Shift+V",
        "tip_expansion_text": "Plain text or HTML supported.\nPaste plain with Ctrl+Shift+V, formatted with Ctrl+V.",
        "placeholder_rich_text": "HTML can be used:\n<b>Bold</b>, <i>Italic</i>, <u>Underline</u>\n<font color='red'>Colored text</font>",
        "net_error_prefix": "Could not check for updates.\nPlease check your internet connection.",
        "check_error_prefix": "An error occurred while checking for updates:\n{}",
        "cmd_grp_power": "--- 🔋 System Power ---",
        "cmd_shutdown": "Shut Down",
        "cmd_restart": "Restart",
        "cmd_sleep": "Sleep Mode",
        "cmd_hibernate": "Hibernate",
        "cmd_lock": "Lock",
        "cmd_logout": "Sign Out",
        "cmd_turn_off_screen": "Turn Off Screen",
        "cmd_empty_recycle_bin": "Empty Recycle Bin",
        "cmd_grp_screen": "--- 📸 Screen & Tools ---",
        "cmd_screenshot": "Screenshot",
        "cmd_snipping_tool": "Snipping Tool",
        "cmd_clipboard_history": "Clipboard History",
        "cmd_emoji_panel": "Emoji Panel",
        "cmd_magnifier": "Magnifier",
        "cmd_on_screen_keyboard": "On-Screen Keyboard",
        "cmd_grp_apps": "--- 📱 Apps & Tools ---",
        "cmd_task_mgr": "Task Manager",
        "cmd_run_dialog": "Run Dialog",
        "cmd_cmd": "Command Prompt",
        "cmd_powershell": "PowerShell",
        "cmd_explorer": "File Explorer",
        "cmd_notepad": "Notepad",
        "cmd_calc": "Calculator",
        "cmd_paint": "Paint",
        "cmd_settings": "Settings",
        "cmd_control_panel": "Control Panel",
        "cmd_device_manager": "Device Manager",
        "cmd_volume_mixer": "Volume Mixer",
        "cmd_services": "Services",
        "cmd_grp_media": "--- 🎵 Media ---",
        "cmd_play_pause": "Play / Pause",
        "cmd_next_track": "Next Track",
        "cmd_prev_track": "Previous Track",
        "cmd_stop": "Stop",
        "cmd_grp_volume": "--- 🔊 Volume ---",
        "cmd_volume_up": "Volume Up",
        "cmd_volume_down": "Volume Down",
        "cmd_volume_mute": "Mute Volume",
        "cmd_volume_max": "Maximum Volume",
        "cmd_volume_min": "Minimum Volume",
        "cmd_grp_windows": "--- 🪟 Window & Desktop ---",
        "cmd_show_desktop": "Show Desktop",
        "cmd_minimize_all": "Minimize All Windows",
        "cmd_task_view": "Task View",
        "cmd_new_vdesktop": "New Virtual Desktop",
        "cmd_next_vdesktop": "Next Desktop",
        "cmd_prev_vdesktop": "Previous Desktop",
        "cmd_close_vdesktop": "Close Virtual Desktop",
        "cmd_snap_left": "Snap Left",
        "cmd_snap_right": "Snap Right",
        "cmd_maximize_window": "Maximize Window",
        "cmd_close_window": "Close Window",
        "cmd_switch_window": "Switch Window",
        "cmd_grp_browsers": "--- 🌐 Browsers ---",
        "cmd_chrome": "Chrome",
        "cmd_firefox": "Firefox",
        "cmd_edge": "Edge",
        "cmd_grp_browser_nav": "--- 🧭 Browser Navigation ---",
        "cmd_back": "Back",
        "cmd_forward": "Forward",
        "cmd_refresh_page": "Refresh Page",
        "cmd_new_tab": "New Tab",
        "cmd_close_tab": "Close Tab",
        "cmd_reopen_tab": "Reopen Closed Tab",
        "cmd_grp_quick_access": "--- 📁 Quick Access ---",
        "cmd_this_pc": "This PC",
        "cmd_downloads": "Downloads",
        "cmd_documents": "Documents",
        "cmd_pictures": "Pictures",
        "cmd_music": "Music",
        "cmd_videos": "Videos",
        "cmd_desktop_folder": "Desktop Folder",
        "cmd_recycle_bin": "Recycle Bin",
        "cmd_grp_text": "--- ✏️ Text & Editing ---",
        "cmd_copy": "Copy",
        "cmd_cut": "Cut",
        "cmd_paste": "Paste",
        "cmd_select_all": "Select All",
        "cmd_undo": "Undo",
        "cmd_redo": "Redo",
        "cmd_find": "Find",
        "cmd_save": "Save",
        "cmd_print": "Print",
        "about_heading": "FlexiKey",
        "about_subtitle": "Advanced Keyboard & Text Expansion Manager",
        "about_description": "Professional toolkit designed to accelerate your workflow with global keyboard shortcuts, rich text automation, and deep system integrations.",
        "about_copyright": "&copy; 2026 FlexiKey. All rights reserved.",
        "help_title": "User Guide",
        "help_heading": "FlexiKey User Guide",
        "help_section_hotkeys_title": "Defining Keyboard Shortcuts",
        "help_hotkeys_step1": "1. Click the <b>Add Shortcut</b> button.",
        "help_hotkeys_step2": "2. Click the shortcut box and press your target key combination (e.g. Ctrl+Shift+M).",
        "help_hotkeys_step3": "3. Choose the action type and fill in the required parameters.",
        "help_hotkeys_step4": "4. Click <b>Save</b> to activate the shortcut.",
        "help_section_expansion_title": "Text Expansion",
        "help_expansion_step1": "1. Click the <b>Add Expansion</b> button.",
        "help_expansion_step2": "2. Choose a trigger abbreviation (e.g. <code>@mail</code>, <code>/addr</code>, <code>addr1</code>).",
        "help_expansion_step3": "3. Enter the expansion text (Rich/HTML formatting supported).",
        "help_expansion_step4": "4. In any app, type the trigger and press <b>Space</b>.",
        "help_section_shortcuts_title": "Application Shortcuts",
        "help_sc_add_hotkey": "• <b>Ctrl+N:</b> Add New Shortcut",
        "help_sc_add_expansion": "• <b>Ctrl+Shift+N:</b> Add New Expansion",
        "help_sc_toggle_theme": "• <b>Ctrl+T:</b> Toggle Theme (Light / Dark)",
        "help_sc_settings": "• <b>Ctrl+,:</b> Settings Window",
        "help_sc_refresh": "• <b>F5:</b> Refresh List",
        "help_sc_toggle": "• <b>Space:</b> Toggle Selected Item Active/Inactive",
        "help_sc_guide": "• <b>F1:</b> User Guide",
        "help_sc_exit": "• <b>Ctrl+Q:</b> Exit Application (Alt+F4 only closes the window; the app keeps running in the tray)",
        "import_preview_summary": "To be imported: {} shortcuts, {} expansions.",
        "import_preview_skipped": "{} entries will be skipped because they are invalid.",
        "import_preview_rejected": "Invalid values will be ignored: {}",
        "import_preview_risky": "⚠ {} actions are risky (destructive system command, running a program/file, or a custom command). Only import files from a source you trust.",
        "import_preview_list_header": "Shortcut actions:",
        "import_preview_more": "… and {} more actions (use “Show Details” for the full list)",
        "import_preview_update_url": "The update address will be set to: {}",
        "update_mandatory_installing": "The mandatory update was downloaded. FlexiKey will restart in a few seconds to install it.",
        "update_auto_installing": "The update was downloaded. FlexiKey will restart in a few seconds to install it.",
        "confirm_destructive_title": "Confirmation Required",
        "confirm_destructive_text": "The “{}” action is about to run. Do you want to continue?",
        "confirm_destructive_power": "The computer or session will shut down/restart immediately; unsaved work may be lost.",
        "confirm_destructive_recycle": "All items in the Recycle Bin will be permanently deleted.",
        "confirm_destructive_cancelled": "Cancelled: {}",
        "settings_warn_title": "Settings File Warning",
        "settings_warn_corrupt_restored": "The settings file was corrupt; it was restored from the last backup.\nCorrupt file kept at:\n{}",
        "settings_warn_corrupt_defaults": "The settings file was corrupt and no usable backup was found; default settings are in use.\nCorrupt file kept at:\n{}",
        "settings_warn_invalid_records": "{} invalid entries were skipped. A copy of the original file was kept as: {}.invalid-*",
        "settings_warn_read_failed_backup": "The settings file could not be read (another program may be using it); the backup was used. The file was not modified:\n{}",
        "settings_warn_read_failed_defaults": "The settings file could not be read (another program may be using it); default settings are temporarily in use. The file was not modified:\n{}",
        "cmd_not_installed": "Required program not found: {}. Install it and try again.",
        "cmd_unsupported_platform": "This command is not supported on {}: {}",
        "notif_url_no_browser": "No default web browser was found",
        "input_status_title": "Keyboard Shortcuts Are Unavailable",
        "input_status_wayland": "A Wayland session was detected. Wayland does not let applications listen for global keyboard shortcuts or inject keystrokes, so hotkeys and text expansion will not work (commands such as launching programs or opening URLs still do).\nFix: choose the 'X11 / Xorg' session at the login screen.",
        "input_status_no_display": "Could not connect to the graphical session (X11 DISPLAY); global hotkeys and text expansion are disabled. Start FlexiKey from inside your desktop session.",
        "input_status_macos_permission": "macOS permission required: in System Settings → Privacy & Security, allow FlexiKey for: {}.\nAfter granting it, switch back to FlexiKey; the permission is detected automatically (restart the app if it is not).",
        "input_status_missing_dependency": "The keyboard component could not be loaded ({}). Install the required package: pip install pynput",
        "input_perm_accessibility": "Accessibility",
        "input_perm_input_monitoring": "Input Monitoring",
        "input_open_privacy_settings": "Open Permission Settings",
    },
}

SUPPORTED_LANGUAGES: tuple[str, ...] = tuple(LOCALES.keys())
FALLBACK_LANGUAGE = "tr"
AUTO_LANGUAGE = "auto"

LANGUAGE_NAMES: dict[str, str] = {
    "tr": "Türkçe",
    "en": "English",
}

LANGUAGE_FLAGS: dict[str, str] = {
    "auto": "🌐",
    "tr": "🇹🇷",
    "en": "🇺🇸",
    "de": "🇩🇪",
    "fr": "🇫🇷",
    "es": "🇪🇸",
    "it": "🇮🇹",
    "nl": "🇳🇱",
    "ru": "🇷🇺",
    "ar": "🇸🇦",
}


def language_flag(code: str | None) -> str:
    """Dil kodu için bayrak emojisi (bulunamazsa boş döner)."""
    if not code:
        return ""
    return LANGUAGE_FLAGS.get(code, "")


def language_display_name(code: str) -> str:
    """Dil kodu ve ana dil adı; bayraklar görsel QIcon olarak verilir."""
    native = LANGUAGE_NAMES.get(code, code.upper())
    code_label = "US" if code == "en" else code.upper()
    return f"{code_label} · {native}"


_LANGUAGE_NAME_TO_CODE: dict[str, str] = {
    "turkce": "tr",
    "türkçe": "tr",
    "turkish": "tr",
    "turk": "tr",
    "english": "en",
    "ingilizce": "en",
    "german": "de",
    "deutsch": "de",
    "almanca": "de",
    "french": "fr",
    "francais": "fr",
    "français": "fr",
    "fransizca": "fr",
    "fransızca": "fr",
    "spanish": "es",
    "espanol": "es",
    "español": "es",
    "ispanyolca": "es",
    "italian": "it",
    "italiano": "it",
    "italyanca": "it",
}

_WIN_PRIMARY_LANG_TO_CODE: dict[int, str] = {
    0x1F: "tr",
    0x09: "en",
    0x07: "de",
    0x0C: "fr",
    0x0A: "es",
    0x10: "it",
    0x13: "nl",
    0x19: "ru",
    0x01: "ar",
}


def _normalize_lang_code(raw: str | None) -> str | None:
    """'tr-TR', 'tr_TR.UTF-8', 'Turkish_Turkiye', 'tr:en_US:en' gibi girdilerden dil kodu çıkarır."""
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip().lower()
    if not s or s in ("c", "c.utf8", "c.utf-8", "posix"):
        return None
    if ":" in s or ";" in s:
        for part in s.replace(";", ":").split(":"):
            code = _normalize_lang_code(part)
            if code:
                return code
        return None
    for sep in (".", "@"):
        if sep in s:
            s = s.split(sep, 1)[0]
    s = s.strip()
    if not s:
        return None
    if s in _LANGUAGE_NAME_TO_CODE:
        cand = _LANGUAGE_NAME_TO_CODE[s]
        if cand in LOCALES:
            return cand
    tokens = s.replace("-", "_").split("_")
    if not tokens:
        return None
    first = tokens[0].strip()
    if first in _LANGUAGE_NAME_TO_CODE:
        first = _LANGUAGE_NAME_TO_CODE[first]
    if first in LOCALES:
        return first
    return None


def _locale_code_from_system() -> str | None:
    """Windows / macOS / Linux'ta gerçek arayüz dilini tespit eder.

    Öncelik sırası:
    1. POSIX ortam değişkenleri (LANGUAGE, LC_ALL, LC_MESSAGES, LANG) - Linux/Ubuntu/macOS
    2. Qt uiLanguages() + bcp47Name/name - Windows/macOS gerçek UI dili listesi
    3. Windows Win32 API (GetUserDefaultUILanguage) - Format/Region farklı olsa bile UI dili
    4. macOS defaults AppleLanguages - QApplication yokken bile
    5. Python locale modülü
    """
    # Windows'ta Qt'nin bölgesel ayarı, Windows görüntüleme dilinden
    # farklı olabilir. Görüntüleme dilini doğrudan Win32 API'den öncele.
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            for func in ("GetUserDefaultUILanguage", "GetSystemDefaultUILanguage"):
                try:
                    lcid = int(getattr(kernel32, func)())
                    code = _WIN_PRIMARY_LANG_TO_CODE.get(lcid & 0x3FF)
                    if code and code in LOCALES:
                        return code
                except Exception:
                    continue
            buf = ctypes.create_unicode_buffer(85)
            if kernel32.GetUserDefaultLocaleName(buf, 85):
                code = _normalize_lang_code(buf.value)
                if code:
                    return code
        except Exception:
            pass

    for env in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        try:
            val = os.environ.get(env)
            if val:
                for part in val.replace(";", ":").split(":"):
                    code = _normalize_lang_code(part)
                    if code:
                        return code
        except Exception:
            pass
    try:
        from PyQt6.QtCore import QLocale
        ql = QLocale.system()
        try:
            for ui_lang in (ql.uiLanguages() or []):
                code = _normalize_lang_code(ui_lang)
                if code:
                    return code
        except Exception:
            pass
        for candidate in (ql.bcp47Name(), ql.name()):
            try:
                code = _normalize_lang_code(candidate)
            except Exception:
                code = None
            if code:
                return code
    except Exception:
        pass
    try:
        if sys.platform == "win32":
            import ctypes
            try:
                kernel32 = ctypes.windll.kernel32
                for func in ("GetUserDefaultUILanguage", "GetSystemDefaultUILanguage"):
                    try:
                        lcid = int(getattr(kernel32, func)())
                        code = _WIN_PRIMARY_LANG_TO_CODE.get(lcid & 0x3FF)
                        if code and code in LOCALES:
                            return code
                    except Exception:
                        continue
                try:
                    buf = ctypes.create_unicode_buffer(85)
                    if kernel32.GetUserDefaultLocaleName(buf, 85):
                        code = _normalize_lang_code(buf.value)
                        if code:
                            return code
                except Exception:
                    pass
            except Exception:
                pass
    except Exception:
        pass
    try:
        if sys.platform == "darwin":
            import subprocess
            try:
                out = subprocess.check_output(
                    ["defaults", "read", "-g", "AppleLanguages"],
                    text=True, timeout=2,
                )
                import re
                for m in re.findall(r'"([^"]+)"', out or ""):
                    code = _normalize_lang_code(m)
                    if code:
                        return code
            except Exception:
                pass
    except Exception:
        pass
    try:
        try:
            loc = locale.getlocale()[0] or ""
            code = _normalize_lang_code(loc)
            if code:
                return code
        except Exception:
            pass
        try:
            loc2 = (locale.getdefaultlocale()[0] or "")
            code = _normalize_lang_code(loc2)
            if code:
                return code
        except Exception:
            pass
    except Exception:
        pass
    return None


def get_system_language() -> str:
    """Sistem dilini desteklenen kodlardan birine çözümler."""
    return _locale_code_from_system() or FALLBACK_LANGUAGE


def _resolve_language_choice(value: str | None) -> str:
    if value and value != AUTO_LANGUAGE and value in LOCALES:
        return value
    return get_system_language()


# Kullanıcının SEÇTİĞİ dil ("auto" | "tr" | "en"). `SettingsManager` ayarı her yükleyip kaydedişinde günceller; böylece
# dil verilmeden çağrılan `t(anahtar)` ve `get_active_language()` sistem diline değil kullanıcının seçimine bakar.
_preferred_language: str = AUTO_LANGUAGE


def set_preferred_language(choice: str | None) -> None:
    """Kullanıcının dil tercihini (ayardaki "language" değeri) hatırlar; geçersiz/boş değer "auto" sayılır."""
    global _preferred_language
    _preferred_language = choice if isinstance(choice, str) and choice else AUTO_LANGUAGE


def get_preferred_language() -> str:
    return _preferred_language


def get_active_language(settings: Any = None) -> str:
    """Settings sözlüğü veya yöneticisi üzerinden etkin dili döner; hiçbiri verilmezse kullanıcının seçtiği dil."""
    if isinstance(settings, str):
        return _resolve_language_choice(settings)
    if isinstance(settings, dict):
        return _resolve_language_choice(settings.get("language", AUTO_LANGUAGE))
    if settings is not None and hasattr(settings, "get_setting"):
        return _resolve_language_choice(settings.get_setting("language", AUTO_LANGUAGE))
    return _resolve_language_choice(_preferred_language)


def language_choices(
    include_auto: bool = False,
    lang: str | None = None,
) -> list[tuple[str, str]]:
    """Dil seçici için (kod, etiket) çiftleri döner.

    Otomatik satırı tespit edilen dili de gösterir, örn.
    '🌐 Otomatik (Sistem - 🇹🇷 Türkçe)'. Bayraklar sayesinde kullanıcı
    arayüz dilini anlamasa bile kendi dilini seçebiliyor.
    """
    detected = get_system_language()
    active = lang or get_active_language()
    choices: list[tuple[str, str]] = []
    if include_auto:
        base = t("lang_auto", active)
        detected_label = language_display_name(detected)
        if base.endswith(")"):
            auto_label = f"{base[:-1]} - {detected_label})"
        else:
            auto_label = f"{base} - {detected_label}"
        choices.append((AUTO_LANGUAGE, auto_label))
    for code in LOCALES.keys():
        choices.append((code, language_display_name(code)))
    return choices


def t(key: str, lang: str | None = None) -> str:
    """Belirtilen dilde metni döner; dil verilmezse kullanıcının seçtiği dilde (seçilmediyse sistem dilinde)."""
    if lang is None:
        lang = get_active_language()
    table = LOCALES.get(lang) or LOCALES[FALLBACK_LANGUAGE]
    return table.get(key, LOCALES[FALLBACK_LANGUAGE].get(key, key))


_qt_translators: list = []


def install_qt_translations(lang: str | None = None) -> None:
    """Qt'nin kendi yazılarını (Tamam / İptal / Evet / Hayır, metin kutusu sağ tık menüsü…) uygulama diline çevirir.

    Paketlenmiş uygulamada da çalışır: PyInstaller Qt çevirilerini (`qtbase_*.qm`) pakete koyar. Çeviri
    dosyası bulunamazsa sessizce İngilizce kalır; her çağrı öncekini kaldırıp yenisini kurar.
    """
    try:
        from PyQt6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator
    except ImportError:
        return
    app = QCoreApplication.instance()
    if app is None:
        return
    for old in _qt_translators:
        try:
            app.removeTranslator(old)
        except RuntimeError:  # önceki QApplication yok edilmiş (testler, yeniden başlatma)
            pass
    _qt_translators.clear()
    code = lang or get_active_language()
    folders = [QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)]
    bundle = getattr(sys, "_MEIPASS", "")
    if bundle:
        folders.append(os.path.join(bundle, "PyQt6", "Qt6", "translations"))
    for folder in folders:
        translator = QTranslator(app)
        if translator.load(QLocale(code), "qtbase", "_", folder):
            app.installTranslator(translator)
            _qt_translators.append(translator)
            break
    _install_key_names(app)


def _install_key_names(app) -> None:
    """Kısayol adlarını (menülerdeki "Ctrl+Shift+N") çevirmeden bırakır.

    Qt'nin Türkçe çevirisi bunları "Kontrol+Üst Karakter+N" yapıyordu; klavyedeki tuşlar ise Ctrl/Shift/Alt
    yazar. En son kurulan çevirici önce sorulduğu için bu, qtbase çevirisinin "QShortcut" bölümünü geçersiz
    kılar. macOS'ta Qt zaten ⌘⇧N gibi simgeler kullanır, bunun etkisi olmaz.
    """
    from PyQt6.QtCore import QTranslator

    class _KeyNames(QTranslator):
        def isEmpty(self) -> bool:  # noqa: N802
            return False

        def translate(self, context, source_text, disambiguation=None, n=-1):
            return source_text if context == "QShortcut" else None

    translator = _KeyNames()  # parent'sız: uygulama yok edilince C++ tarafı Python'dan önce silinmesin
    app.installTranslator(translator)
    _qt_translators.append(translator)
