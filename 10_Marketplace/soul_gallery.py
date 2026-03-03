"""
10_Marketplace/soul_gallery.py
==============================
提供 SOUL 的打包分享、驗證及匯入功能 (Soul Gallery)。
將 SOUL.md 與對應的 Metadata 打包成 .soul.zip，方便加密與流傳。
"""

import hashlib
import json
import logging
import shutil
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Tuple, Optional

from paths import get_data_dir, get_soul_path

logger = logging.getLogger(__name__)

GALLERY_DIR = get_data_dir() / "soul_gallery"

@dataclass
class SoulInfo:
    name: str
    author: str
    version: str
    description: str
    personality_tags: List[str]
    rules_hash: str
    filename: Optional[str] = None

class SoulGallery:
    def __init__(self):
        self._ensure_gallery_dir()

    def _ensure_gallery_dir(self):
        if not GALLERY_DIR.exists():
            GALLERY_DIR.mkdir(parents=True, exist_ok=True)

    def validate_soul(self, soul_content: str) -> Tuple[bool, List[str]]:
        """
        驗證 SOUL.md 的格式是否有包含至少三個必要的區塊:
        - 🎯 核心目標 (Core Objectives)
        - 📜 行為準則 (Rules & Guidelines)
        - 🛠️ 預設技能 (Default Skills)
        """
        errors = []
        if "🎯" not in soul_content and "Core Objectives" not in soul_content:
            errors.append("Missing Core Objectives section")
        if "📜" not in soul_content and "Rules" not in soul_content:
            errors.append("Missing Rules & Guidelines section")
        if "🛠️" not in soul_content and "Skills" not in soul_content:
            errors.append("Missing Default Skills section")
        
        return len(errors) == 0, errors

    def publish_soul(self, metadata: dict, soul_path: Optional[str] = None) -> str:
        """
        將本地的 SOUL.md 打包成 .soul.zip。
        metadata 需要包含 name, author, version, description, personality_tags。
        """
        if soul_path is None:
            path = get_soul_path()
        else:
            path = Path(soul_path)

        if not path.exists():
            raise FileNotFoundError(f"SOUL file not found at {path}")

        content = path.read_text(encoding="utf-8")
        is_valid, errors = self.validate_soul(content)
        if not is_valid:
            raise ValueError(f"SOUL Validation failed: {errors}")

        # Generate hash of rules
        rules_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        
        # Build SoulInfo
        try:
            info = SoulInfo(
                name=metadata.get("name", "Unknown Soul"),
                author=metadata.get("author", "Anonymous"),
                version=metadata.get("version", "1.0"),
                description=metadata.get("description", ""),
                personality_tags=metadata.get("personality_tags", []),
                rules_hash=rules_hash
            )
        except Exception as e:
            raise ValueError(f"Invalid metadata: {e}")

        # Create zip in gallery
        safe_name = info.name.replace(" ", "_").lower()
        zip_filename = f"{safe_name}_v{info.version}.soul.zip"
        zip_path = GALLERY_DIR / zip_filename

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.writestr("SOUL.md", content)
            zipf.writestr("metadata.json", json.dumps(asdict(info), indent=2, ensure_ascii=False))

        logger.info(f"🎭 Successfully published Soul '{info.name}' to {zip_path}")
        return str(zip_path)

    def import_soul(self, zip_path: str, set_as_active: bool = False) -> str:
        """從 .soul.zip 解壓縮並安裝。可選是否直接覆蓋目前使用的 SOUL.md"""
        zp = Path(zip_path)
        if not zp.exists() or not str(zp).endswith(".soul.zip"):
            raise ValueError("File must be a valid .soul.zip")

        # Extract to a temp dir first to validate
        import tempfile
        extracted_metadata = None
        extracted_content = None
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with zipfile.ZipFile(zp, 'r') as zipf:
                zipf.extractall(temp_path)
            
            md_path = temp_path / "SOUL.md"
            json_path = temp_path / "metadata.json"
            
            if not md_path.exists() or not json_path.exists():
                raise ValueError("Archive is missing SOUL.md or metadata.json")
                
            extracted_content = md_path.read_text(encoding="utf-8")
            is_valid, errors = self.validate_soul(extracted_content)
            if not is_valid:
                raise ValueError(f"Malformed SOUL content in archive: {errors}")
            
            try:
                extracted_metadata = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception as e:
                raise ValueError(f"Malformed metadata JSOn in archive: {e}")

        # Verification passed, copy the zip to Gallery catalog
        dest_zip = GALLERY_DIR / zp.name
        if zp.resolve() != dest_zip.resolve():
            shutil.copy2(zp, dest_zip)
            
        logger.info(f"🎭 Successfully imported Soul '{extracted_metadata.get('name')}' to Gallery.")

        if set_as_active and extracted_content:
            target_soul = get_soul_path()
            target_soul.write_text(extracted_content, encoding="utf-8")
            logger.warning(f"⚠️ Active SOUL.md has been replaced by '{extracted_metadata.get('name')}'.")
            
        return str(dest_zip)

    def list_gallery(self) -> List[SoulInfo]:
        """列出 Gallery 內所有已安裝/匯入的 Soul"""
        souls = []
        if not GALLERY_DIR.exists():
            return souls
            
        for file in GALLERY_DIR.glob("*.soul.zip"):
            try:
                with zipfile.ZipFile(file, 'r') as zipf:
                    if "metadata.json" in zipf.namelist():
                        meta_text = zipf.read("metadata.json").decode("utf-8")
                        meta_dict = json.loads(meta_text)
                        
                        info = SoulInfo(
                            name=meta_dict.get("name", ""),
                            author=meta_dict.get("author", ""),
                            version=meta_dict.get("version", ""),
                            description=meta_dict.get("description", ""),
                            personality_tags=meta_dict.get("personality_tags", []),
                            rules_hash=meta_dict.get("rules_hash", ""),
                            filename=file.name
                        )
                        souls.append(info)
            except Exception as e:
                logger.error(f"Failed to read soul archive {file.name}: {e}")
                
        return souls
