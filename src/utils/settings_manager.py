"""
Settings Manager - Ayar yönetimi ve JSON kaydı

Güvenlik/dayanıklılık kuralları:
  * Kayıt atomiktir (geçici dosya + flush + fsync + os.replace); yarım dosya oluşmaz.
  * Başarılı bir kayıttan önce geçerli eski dosya ``config.json.bak`` olarak saklanır.
  * Bozuk dosya sessizce varsayılanla ezilmez: ``config.json.corrupt-<zaman>`` olarak
    ayrılır, varsa ``.bak``'tan geri yüklenir, yoksa varsayılana dönülür ve kullanıcıya
    gösterilebilecek bir uyarı biriktirilir (``pop_warnings``).
  * Yükle-değiştir-kaydet dizileri ``transaction()`` ile tek (süreç genelinde paylaşılan)
    RLock altında yapılır.
  * Şemaya uymayan kısayol/genişletme kayıtları atlanır (tek bozuk kayıt hepsini öldürmez).
"""

import copy
import glob
import json
import os
import shutil
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from src.utils import secret_store
from src.utils.helpers import (
    log_error, log_warning, resolve_user_config, APP_ID,
    get_application_path, atomic_write_bytes,
)

DEFAULT_SETTINGS: Dict[str, Any] = {
    'language': 'auto',
    'theme': 'system',
    'accent': 'cyan',
    'start_minimized': True,
    'show_notifications': False,
    'hotkeys': [],
    'expansions': [],
    'update_url': '',
    'auto_update_check': True,
    'auto_update_install': True,
'last_update_check': None,
    'declined_update_version': None,
    'dismissed_notice': '',
}

# Uygulamanın bildiği eylem türleri (içe aktarmada katı doğrulama için)
VALID_ACTION_TYPES = ('text', 'command', 'shortcut', 'open_url', 'open_file', 'run_program')

HOTKEY_REQUIRED_KEYS = ('shortcut', 'action_type', 'action_value')
EXPANSION_REQUIRED_KEYS = ('trigger', 'replacement')

_MAX_QUARANTINE_COPIES = 5


def validate_hotkey_record(record: Any, strict: bool = False) -> Optional[str]:
    """Kısayol kaydı geçerliyse None, değilse nedenini döndürür.

    strict=False: yalnızca yapısal doğrulama (yükleme; ileri uyumluluk için bilinmeyen
    eylem türleri korunur). strict=True: içe aktarma — bilinen eylem türü ve boş olmayan değer.
    """
    if not isinstance(record, dict):
        return "kayıt bir sözlük değil"
    for key in HOTKEY_REQUIRED_KEYS:
        if key not in record:
            return f"'{key}' anahtarı eksik"
        if not isinstance(record[key], str):
            return f"'{key}' metin değil"
    if not record['shortcut'].strip():
        return "'shortcut' boş"
    if strict:
        if record['action_type'] not in VALID_ACTION_TYPES:
            return f"bilinmeyen eylem türü: {record['action_type']!r}"
        if not record['action_value'].strip():
            return "'action_value' boş"
    return None


def validate_expansion_record(record: Any, strict: bool = False) -> Optional[str]:
    """Genişletme kaydı geçerliyse None, değilse nedenini döndürür."""
    if not isinstance(record, dict):
        return "kayıt bir sözlük değil"
    for key in EXPANSION_REQUIRED_KEYS:
        if key not in record:
            return f"'{key}' anahtarı eksik"
        if not isinstance(record[key], str):
            return f"'{key}' metin değil"
    if not record['trigger'].strip():
        return "'trigger' boş"
    if strict and not record['replacement']:
        return "'replacement' boş"
    return None


def split_valid_records(records: Any, validator: Callable[..., Optional[str]],
                        strict: bool = False) -> Tuple[List[dict], List[Tuple[int, str]]]:
    """Kayıt listesini (geçerli kayıtlar, [(indeks, neden), ...]) olarak ayırır."""
    if not isinstance(records, list):
        return [], [(-1, "liste değil")]
    valid: List[dict] = []
    dropped: List[Tuple[int, str]] = []
    for index, record in enumerate(records):
        reason = validator(record, strict)
        if reason is None:
            valid.append(record)
        else:
            dropped.append((index, reason))
    return valid, dropped


class _CorruptConfig(Exception):
    """Dosya okundu ama içeriği geçerli bir ayar sözlüğü değil."""


def _parse_config_bytes(raw: bytes) -> Dict[str, Any]:
    try:
        data = json.loads(raw.decode('utf-8-sig'))  # Not Defteri'nin BOM'una toleranslı
    except (UnicodeDecodeError, ValueError) as exc:
        raise _CorruptConfig(str(exc)) from exc
    if not isinstance(data, dict):
        raise _CorruptConfig("kök nesne bir sözlük değil")
    return data


def _is_valid_config_bytes(raw: bytes) -> bool:
    try:
        _parse_config_bytes(raw)
        return True
    except _CorruptConfig:
        return False


def _read_config_file(path: str, attempts: int = 3) -> Dict[str, Any]:
    """Dosyayı okuyup ayrıştırır. Bozuk içerik -> _CorruptConfig; G/Ç hatası -> OSError."""
    last_error: Optional[OSError] = None
    for attempt in range(attempts):
        try:
            with open(path, 'rb') as handle:
                raw = handle.read()
            break
        except OSError as exc:  # geçici kilit (antivirus vb.) olabilir
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(0.05)
    else:
        raise last_error  # type: ignore[misc]
    return _parse_config_bytes(raw)


# Gizli (parola vb.) kayıtlar: bellekte ve arayüzde düz metin, diskte DPAPI ile şifreli ("dpapi1:...").
# Çözülemeyen değer (başka hesap/makine) kaydı silmez: şifreli hali bellekte 'secret_blob' olarak taşınır ve
# yeniden yazılırken olduğu gibi geri konur; değer ise boş görünür.
SECRET_FLAG = 'is_secret'
LOCKED_BLOB = 'secret_blob'


def _secret_slots(settings: Dict[str, Any]) -> Iterator[Tuple[Dict[str, Any], str]]:
    """Gizli olabilecek (kayıt, değer anahtarı) çiftleri: düz metin yazan kısayollar ve düz genişletmeler."""
    for record in settings.get('hotkeys') or []:
        if isinstance(record, dict) and record.get('action_type') == 'text' and not record.get('is_rich'):
            yield record, 'action_value'
    for record in settings.get('expansions') or []:
        if isinstance(record, dict) and not record.get('is_rich'):
            yield record, 'replacement'


def is_secret_record(record: Any) -> bool:
    return isinstance(record, dict) and record.get(SECRET_FLAG) is True and not record.get('is_rich')


def is_locked_secret(record: Any) -> bool:
    """Değeri bu hesapta çözülemeyen gizli kayıt: yazılacak bir şey yok."""
    if not is_secret_record(record) or not record.get(LOCKED_BLOB):
        return False
    return not record.get('replacement', record.get('action_value'))


def secret_count(records: Any) -> int:
    """Değeri okunabilen gizli kayıt sayısı (dışa aktarmadan önce kullanıcıya sorulur)."""
    return sum(1 for r in records or [] if is_secret_record(r) and not is_locked_secret(r))


def exportable_records(records: Any, include_secrets: bool) -> List[Dict[str, Any]]:
    """Dosyaya yazılacak kayıtlar: gizliler yalnızca izin verilirse; çözülemeyenler ve iç alanlar hiç."""
    out: List[Dict[str, Any]] = []
    for record in records or []:
        if is_secret_record(record) and (not include_secrets or is_locked_secret(record)):
            continue
        out.append({k: v for k, v in record.items() if k != LOCKED_BLOB} if isinstance(record, dict) else record)
    return out


def _seal(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Diske yazılacak kopya: gizli değerler şifrelenir (bu sistemde şifrelenemiyorsa olduğu gibi kalır)."""
    sealed = copy.deepcopy(settings)
    for record, key in _secret_slots(sealed):
        blob = record.pop(LOCKED_BLOB, None)
        if record.get(SECRET_FLAG) is not True:
            continue
        value = record.get(key, '')
        if value:
            token = secret_store.protect(value)
            if token:
                record[key] = token
        elif blob:
            record[key] = blob
    return sealed


def _unseal(settings: Dict[str, Any]) -> int:
    """Okunan ayarlardaki gizli değerleri çözer (yerinde). Çözülemeyenlerin sayısını döndürür."""
    locked = 0
    for record, key in _secret_slots(settings):
        if record.get(SECRET_FLAG) is not True or not secret_store.is_blob(record.get(key)):
            continue
        plain = secret_store.unprotect(record[key])
        if plain is None:
            record[LOCKED_BLOB] = record[key]
            record[key] = ''
            locked += 1
        else:
            record[key] = plain
    return locked


def _secret_flag(record: Dict[str, Any], can_be_secret: bool) -> Dict[str, Any]:
    """Temizlenmiş kayda eklenecek gizlilik işareti (yalnızca düz metin yazan kayıtlarda geçerlidir)."""
    if can_be_secret and record.get(SECRET_FLAG) is True and not record.get('is_rich'):
        return {SECRET_FLAG: True}
    return {}


def _clean_hotkey(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'shortcut': record['shortcut'].strip(),
        'action_type': record['action_type'],
        'action_value': record['action_value'],
        'enabled': bool(record.get('enabled', True)),
        'is_rich': bool(record.get('is_rich', False)),
        **_secret_flag(record, record['action_type'] == 'text'),
    }


def _clean_expansion(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'trigger': record['trigger'].strip(),
        'replacement': record['replacement'],
        'enabled': bool(record.get('enabled', True)),
        'is_rich': bool(record.get('is_rich', False)),
        **_secret_flag(record, True),
    }


def prepare_import(imported: Any, options: Dict[str, bool]) -> Dict[str, Any]:
    """İçe aktarılacak dosyayı doğrular; diske/belleğe hiçbir şey yazmaz.

    options: ImportExportDialog seçimleri (hotkeys/expansions/theme/behavior/update).
    Dönen sözlük:
      updates            -> ayarlara uygulanacak üst düzey anahtarlar (yalnızca geçerli değerler)
      hotkeys/expansions -> geçerli (temizlenmiş) kayıtlar (seçildiyse)
      dropped_hotkeys/dropped_expansions -> [(indeks, neden), ...]
      rejected           -> geçersiz olduğu için yoksayılan anahtarlar
    Kayıtlar katı doğrulanır: bilinen eylem türü, boş olmayan değer, doğru tipler.
    """
    if not isinstance(imported, dict):
        raise ValueError("İçe aktarılan dosyanın kökü bir sözlük değil")

    plan: Dict[str, Any] = {
        'updates': {}, 'hotkeys': [], 'expansions': [],
        'dropped_hotkeys': [], 'dropped_expansions': [], 'rejected': [],
    }
    updates = plan['updates']

    if options.get('hotkeys') and 'hotkeys' in imported:
        valid, plan['dropped_hotkeys'] = split_valid_records(
            imported['hotkeys'], validate_hotkey_record, strict=True)
        plan['hotkeys'] = [_clean_hotkey(r) for r in valid]
        updates['hotkeys'] = plan['hotkeys']

    if options.get('expansions') and 'expansions' in imported:
        valid, plan['dropped_expansions'] = split_valid_records(
            imported['expansions'], validate_expansion_record, strict=True)
        plan['expansions'] = [_clean_expansion(r) for r in valid]
        updates['expansions'] = plan['expansions']

    def accept(key: str, check: Callable[[Any], bool]) -> None:
        if key not in imported:
            return
        if check(imported[key]):
            updates[key] = imported[key]
        else:
            plan['rejected'].append(key)

    is_bool = lambda v: isinstance(v, bool)
    if options.get('theme'):
        accept('theme', lambda v: isinstance(v, str) and 0 < len(v) <= 32)
    if options.get('behavior'):
        accept('start_minimized', is_bool)
        accept('show_notifications', is_bool)
    if options.get('update'):
        # Güncelleme adresi yalnızca https olabilir (güncelleme akışı bu adresten indirir)
        accept('update_url', lambda v: isinstance(v, str) and (v == '' or v.lower().startswith('https://')))
        accept('auto_update_check', is_bool)
        accept('auto_update_install', is_bool)  # dışa aktarma bunu da yazar
        accept('last_update_check', lambda v: v is None or isinstance(v, str))
    return plan


def format_settings_warning(kind: str, detail: str, lang: Optional[str] = None) -> str:
    """SettingsManager.pop_warnings() çıktısını kullanıcıya gösterilecek metne çevirir."""
    from src.utils.locales import t
    key = f"settings_warn_{kind}"
    template = t(key, lang)
    if template == key:  # bilinmeyen tür: ham ayrıntıyı göster
        return detail
    if kind == 'invalid_records':
        count, _, path = detail.partition('|')
        return template.format(count, path)
    return template.format(detail)


def register_saved_items(settings: Dict[str, Any], hotkey_manager: Any) -> Dict[str, int]:
    """Kayıtlı kısayol ve genişletmeleri yöneticiye ekler.

    Kayıt başına hata yalıtımı: tek bozuk kayıt (eksik anahtar, geçersiz kısayol...) diğerlerinin
    yüklenmesini engellemez; hata loglanır. (Log'a kayıt içeriği yazılmaz: genişletmeler
    parola/e-posta gibi hassas metin içerebilir.)
    """
    counts = {'hotkeys': 0, 'hotkeys_failed': 0, 'expansions': 0, 'expansions_failed': 0}

    for index, record in enumerate(settings.get('hotkeys') or []):
        try:
            if isinstance(record, dict) and not record.get('enabled', True):
                continue
            reason = validate_hotkey_record(record)
            if reason is not None:
                raise ValueError(reason)
            if is_locked_secret(record):
                continue
            hotkey_manager.add_hotkey(
                record['shortcut'], record['action_type'], record['action_value'],
                record.get('is_rich', False), **({'secret': True} if is_secret_record(record) else {}),
            )
            counts['hotkeys'] += 1
        except Exception as exc:
            counts['hotkeys_failed'] += 1
            name = record.get('shortcut') if isinstance(record, dict) else None
            log_error(f"Kısayol kaydı #{index} ({name!r}) yüklenemedi, atlandı", exc)

    for index, record in enumerate(settings.get('expansions') or []):
        try:
            if isinstance(record, dict) and not record.get('enabled', True):
                continue
            reason = validate_expansion_record(record)
            if reason is not None:
                raise ValueError(reason)
            if is_locked_secret(record):
                continue
            hotkey_manager.add_expansion(
                record['trigger'], record['replacement'], record.get('is_rich', False),
            )
            counts['expansions'] += 1
        except Exception as exc:
            counts['expansions_failed'] += 1
            name = record.get('trigger') if isinstance(record, dict) else None
            log_error(f"Genişletme kaydı #{index} ({name!r}) yüklenemedi, atlandı", exc)

    return counts


class SettingsManager:
    """Uygulama ayarlarını JSON ile yöneten sınıf"""

    # Süreçteki tüm SettingsManager örnekleri (UpdateChecker kendi örneğini yaratır) aynı
    # dosyayı paylaştığı için kilit ve uyarı listesi sınıf düzeyindedir.
    _lock = threading.RLock()
    _pending_warnings: List[Tuple[str, str]] = []
    _seen_warnings: set = set()

    def __init__(self, settings_file: str = 'config.json', *, settings_path: Optional[str] = None):
        """settings_path verilirse (test/özel kurulum) doğrudan o dosya kullanılır;
        kullanıcı dizini çözümlemesi ve tohum dosyası atlanır."""
        self._is_primary = not settings_path
        if settings_path:
            self.settings_file = os.path.abspath(settings_path)
            self._seed_file = None
        else:
            user_path, seed_path = resolve_user_config(
                settings_file, APP_ID, get_application_path()
            )
            self.settings_file = user_path
            self._seed_file = seed_path

        self.default_settings = copy.deepcopy(DEFAULT_SETTINGS)
        self._quarantine_keys: set = set()

    # ------------------------------------------------------------------ yollar / uyarılar
    @property
    def backup_file(self) -> str:
        return self.settings_file + '.bak'

    @classmethod
    def pop_warnings(cls) -> List[Tuple[str, str]]:
        """Kullanıcıya gösterilmeyi bekleyen (tür, ayrıntı) uyarılarını alır ve temizler."""
        with cls._lock:
            warnings, cls._pending_warnings = cls._pending_warnings, []
            return warnings

    @classmethod
    def _warn(cls, kind: str, detail: str) -> None:
        with cls._lock:
            key = (kind, detail)
            if key in cls._seen_warnings:
                return
            cls._seen_warnings.add(key)
            cls._pending_warnings.append(key)

    def _defaults(self) -> Dict[str, Any]:
        return copy.deepcopy(self.default_settings)

    # ------------------------------------------------------------------ yükleme
    def load_settings(self) -> Dict[str, Any]:
        """Ayarları kullanıcı config'inden yükle; yoksa dizindeki tohumu bir kez oku."""
        settings = self._load_settings()
        self._remember_language(settings)
        return settings

    def _remember_language(self, settings: Dict[str, Any]) -> None:
        """Kullanıcının dil seçimini locales'a bildirir (dil verilmeyen `t(anahtar)` çağrıları buna bakar).
        Yalnızca gerçek kullanıcı ayar dosyası sayılır: `settings_path` ile verilen test/özel dosyalar sızmaz."""
        if self._is_primary:
            from src.utils.locales import set_preferred_language
            set_preferred_language(settings.get('language'))

    def is_first_run(self) -> bool:
        """"İlk kurulum": ne kullanıcı ayar dosyası ne de (okunacak) tohum dosyası var. İlk `load_settings()` /
        `save_settings()` çağrısından ÖNCE sorulmalıdır (sonrasında dosya oluşur). `settings_path` ile verilen
        özel/test dosyaları hiçbir zaman ilk kurulum sayılmaz."""
        if not self._is_primary or os.path.isfile(self.settings_file):
            return False
        return not (self._seed_file and os.path.isfile(self._seed_file))

    def _load_settings(self) -> Dict[str, Any]:
        with self._lock:
            if os.path.isfile(self.settings_file):
                return self._load_user_file()

            if self._seed_file and os.path.isfile(self._seed_file):
                try:
                    settings = self._normalize(
                        _read_config_file(self._seed_file), self._seed_file, quiet=True
                    )
                except (_CorruptConfig, OSError) as exc:
                    log_error("Tohum ayar dosyası okunamadı, varsayılan kullanılıyor", exc)
                    return self._defaults()
                self.save_settings(settings)
                return settings

            return self._defaults()

    def _load_user_file(self) -> Dict[str, Any]:
        path = self.settings_file
        try:
            return self._normalize(_read_config_file(path), path)
        except _CorruptConfig as exc:
            return self._recover_from_corrupt(path, exc)
        except OSError as exc:
            # Dosya okunamadı (kilit/izin). Dosyaya DOKUNMA; yedeği ya da varsayılanı kullan.
            log_error("Ayar dosyası okunamadı", exc)
            restored = self._read_backup()
            if restored is not None:
                self._warn('read_failed_backup', path)
                return restored
            self._warn('read_failed_defaults', path)
            return self._defaults()

    def _read_backup(self) -> Optional[Dict[str, Any]]:
        backup = self.backup_file
        if not os.path.isfile(backup):
            return None
        try:
            return self._normalize(_read_config_file(backup), backup, quiet=True)
        except (_CorruptConfig, OSError) as exc:
            log_error("Yedek ayar dosyası da okunamadı", exc)
            return None

    def _recover_from_corrupt(self, path: str, exc: Exception) -> Dict[str, Any]:
        """Bozuk dosyayı sakla (üzerine yazılmasın), yedekten dön, olmazsa varsayılan."""
        log_error(f"Ayar dosyası bozuk: {path}", exc)
        saved_as = self._quarantine(path, 'corrupt', move=True)

        restored = self._read_backup()
        if restored is not None:
            log_warning("Bozuk ayar dosyası yerine .bak yedeğinden geri yüklendi")
            self._warn('corrupt_restored', saved_as or path)
            if saved_as is not None:  # config.json artık yok; geri yüklenen içerikle yeniden oluştur
                try:
                    self._write(restored)
                except Exception as write_exc:
                    log_error("Geri yüklenen ayarlar yazılamadı", write_exc)
            return restored

        log_warning("Bozuk ayar dosyası ve kullanılabilir yedek yok: varsayılan ayarlar kullanılıyor")
        self._warn('corrupt_defaults', saved_as or path)
        return self._defaults()

    def _quarantine(self, path: str, tag: str, move: bool) -> Optional[str]:
        """Dosyayı ``<path>.<tag>-<zaman>`` olarak saklar (taşır veya kopyalar); yolu döndürür."""
        try:
            stat = os.stat(path)
            key = (tag, stat.st_size, stat.st_mtime_ns)
            if not move and key in self._quarantine_keys:
                return None  # aynı içerik için tekrar tekrar kopya üretme
            stamp = time.strftime('%Y%m%d-%H%M%S')
            dest = f"{path}.{tag}-{stamp}"
            counter = 1
            while os.path.exists(dest):
                dest = f"{path}.{tag}-{stamp}-{counter}"
                counter += 1
            if move:
                try:
                    os.replace(path, dest)
                except OSError:
                    shutil.copy2(path, dest)  # taşınamadıysa (kilit) en azından kopyala
            else:
                shutil.copy2(path, dest)
            self._quarantine_keys.add(key)
            self._prune_quarantine(path, tag)
            log_warning(f"Ayar dosyası saklandı: {dest}")
            return dest
        except Exception as exc:
            log_error("Ayar dosyası saklanamadı", exc)
            return None

    @staticmethod
    def _prune_quarantine(path: str, tag: str) -> None:
        copies = sorted(glob.glob(glob.escape(f"{path}.{tag}-") + "*"))
        for old in copies[:-_MAX_QUARANTINE_COPIES]:
            try:
                os.remove(old)
            except OSError:
                pass

    def _normalize(self, data: Dict[str, Any], source: str, quiet: bool = False) -> Dict[str, Any]:
        """Varsayılanlarla birleştirir (derin kopya) ve geçersiz kayıtları ayıklar."""
        settings = {**self._defaults(), **copy.deepcopy(data)}

        dropped_total = 0
        for key, validator in (('hotkeys', validate_hotkey_record),
                               ('expansions', validate_expansion_record)):
            valid, dropped = split_valid_records(settings.get(key), validator)
            if dropped:
                dropped_total += len(dropped)
                for index, reason in dropped:
                    log_error(f"Geçersiz '{key}' kaydı atlandı (#{index}): {reason}")
            settings[key] = valid

        locked = _unseal(settings)
        if locked and not quiet:
            self._warn('secret_locked', str(locked))

        if dropped_total and not quiet:
            # Sonraki kayıt bu kayıtları diskten silecek; önce bir kopyasını sakla.
            self._quarantine(source, 'invalid', move=False)
            self._warn('invalid_records', f"{dropped_total}|{source}")
        return settings

    # ------------------------------------------------------------------ kaydetme
    def _write(self, settings: Dict[str, Any]) -> None:
        # Önce bellekte serileştir: serileştirme hatası mevcut dosyaya hiç dokunmaz.
        payload = json.dumps(_seal(settings), indent=4, ensure_ascii=False).encode('utf-8')
        atomic_write_bytes(
            self.settings_file, payload,
            backup_path=self.backup_file, backup_validator=_is_valid_config_bytes,
        )

    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """Ayarları kullanıcı dizinine atomik olarak kaydet (uygulama klasörüne yazılmaz)."""
        if not isinstance(settings, dict):
            log_error("Ayar kaydetme reddedildi: ayarlar sözlük değil")
            return False
        with self._lock:
            try:
                self._write(settings)
                self._remember_language(settings)
                return True
            except Exception as e:
                log_error("Ayar kaydetme hatası", e)
                return False

    @contextmanager
    def transaction(self) -> Iterator[Dict[str, Any]]:
        """Yükle-değiştir-kaydet dizisini kilit altında yapar; blok hatasız biterse kaydeder.

            with settings_manager.transaction() as settings:
                settings['theme'] = 'dark'
        """
        with self._lock:
            settings = self.load_settings()
            yield settings
            self.save_settings(settings)

    def update(self, **values: Any) -> None:
        """Birkaç üst düzey anahtarı tek işlemde güncelle."""
        with self.transaction() as settings:
            settings.update(values)

    # ------------------------------------------------------------------ kısayollar
    def add_hotkey(self, shortcut: str, action_type: str, action_value: str, enabled: bool = True, is_rich: bool = False,
                   is_secret: bool = False):
        """Yeni kısayol ekle"""
        hotkey = {
            'shortcut': shortcut,
            'action_type': action_type,
            'action_value': action_value,
            'enabled': enabled,
            'is_rich': is_rich
        }
        if is_secret and action_type == 'text' and not is_rich:
            hotkey[SECRET_FLAG] = True
        with self.transaction() as settings:
            settings['hotkeys'].append(hotkey)

    def remove_hotkey(self, shortcut: str):
        """Kısayol sil"""
        with self.transaction() as settings:
            settings['hotkeys'] = [h for h in settings['hotkeys'] if h['shortcut'] != shortcut]

    def update_hotkey(self, old_shortcut: str, new_hotkey: Dict[str, Any]):
        """Mevcut kısayolu güncelle"""
        with self.transaction() as settings:
            for i, h in enumerate(settings['hotkeys']):
                if h['shortcut'] == old_shortcut:
                    settings['hotkeys'][i] = new_hotkey
                    break

    # ------------------------------------------------------------------ genişletmeler
    def add_expansion(self, trigger: str, replacement: str, enabled: bool = True, is_rich: bool = False,
                      is_secret: bool = False):
        """Yeni metin genişletme ekle"""
        expansion = {
            'trigger': trigger,
            'replacement': replacement,
            'enabled': enabled,
            'is_rich': is_rich
        }
        if is_secret and not is_rich:
            expansion[SECRET_FLAG] = True
        with self.transaction() as settings:
            settings['expansions'].append(expansion)

    def remove_expansion(self, trigger: str):
        """Metin genişletme sil"""
        with self.transaction() as settings:
            settings['expansions'] = [e for e in settings['expansions'] if e['trigger'] != trigger]

    def update_expansion(self, old_trigger: str, new_expansion: Dict[str, Any]):
        """Mevcut metin genişletmeyi güncelle"""
        with self.transaction() as settings:
            for i, e in enumerate(settings['expansions']):
                if e['trigger'] == old_trigger:
                    settings['expansions'][i] = new_expansion
                    break

    # ------------------------------------------------------------------ basit ayarlar
    def set_theme(self, theme: str):
        """Tema ayarla"""
        self.update(theme=theme)

    def set_start_minimized(self, enabled: bool):
        """Küçültülmüş başlat seçeneği"""
        self.update(start_minimized=enabled)

    def set_show_notifications(self, enabled: bool):
        """Bildirim göster seçeneği"""
        self.update(show_notifications=enabled)

    def set_update_url(self, url: str):
        """Güncelleme URL'si ayarla"""
        self.update(update_url=url)

    def set_auto_update_check(self, enabled: bool):
        """Otomatik güncelleme kontrolü"""
        self.update(auto_update_check=enabled)
