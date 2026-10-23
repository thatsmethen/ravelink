use ravelink_core::Session;
use std::{
    fs::{self, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
};

const MAX_SESSION_BYTES: u64 = 32 * 1024 * 1024;

pub fn default_path() -> Result<PathBuf, String> {
    #[cfg(target_os = "macos")]
    let base =
        std::env::var_os("HOME").map(|p| PathBuf::from(p).join("Library/Application Support"));
    #[cfg(target_os = "windows")]
    let base = std::env::var_os("APPDATA").map(PathBuf::from);
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    let base = std::env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|p| PathBuf::from(p).join(".local/share")));
    base.map(|p| p.join("RaveLinkRust/session.json"))
        .ok_or_else(|| "Cannot locate your application-data folder.".into())
}

pub fn load(path: &Path) -> Result<Option<Session>, String> {
    let file = match fs::File::open(path) {
        Ok(file) => file,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(format!("Cannot open {}: {e}", path.display())),
    };
    let mut json = String::new();
    file.take(MAX_SESSION_BYTES + 1)
        .read_to_string(&mut json)
        .map_err(|e| format!("Cannot read studio: {e}"))?;
    if json.len() as u64 > MAX_SESSION_BYTES {
        return Err("Studio exceeds the 32 MiB file safety budget.".into());
    }
    Session::from_json(&json)
        .map(Some)
        .map_err(|e| format!("Cannot load studio: {e}"))
}

/// Serialize and validate before touching the destination; replace with a
/// fully written sibling file. A failed write leaves the previous studio intact.
pub fn save(path: &Path, session: &Session) -> Result<(), String> {
    let json = session.to_json().map_err(|e| e.to_string())?;
    if json.len() as u64 > MAX_SESSION_BYTES {
        return Err("Studio exceeds the 32 MiB file safety budget.".into());
    }
    let parent = path.parent().ok_or("Studio path has no parent folder")?;
    fs::create_dir_all(parent).map_err(|e| format!("Cannot create studio folder: {e}"))?;
    let temporary = parent.join(format!(".ravelink-{}.tmp", uuid::Uuid::new_v4()));
    let result = (|| -> std::io::Result<()> {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary)?;
        file.write_all(json.as_bytes())?;
        file.sync_all()?;
        drop(file);
        fs::rename(&temporary, path)?;
        #[cfg(unix)]
        fs::File::open(parent)?.sync_all()?;
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result.map_err(|e| format!("Cannot save studio: {e}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    struct TestDir(PathBuf);
    impl TestDir {
        fn new() -> Self {
            let path =
                std::env::temp_dir().join(format!("ravelink-store-{}", uuid::Uuid::new_v4()));
            fs::create_dir(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for TestDir {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    #[test]
    fn replace_roundtrips_and_invalid_state_preserves_original() {
        let dir = TestDir::new();
        let path = dir.0.join("studio.json");
        assert_eq!(load(&path).unwrap(), None);
        let mut session = Session::new("Studio", 48000);
        save(&path, &session).unwrap();
        session.name = "Revised studio".into();
        save(&path, &session).unwrap();
        assert_eq!(load(&path).unwrap().unwrap(), session);
        let original = fs::read(&path).unwrap();
        session.sample_rate = 0;
        assert!(save(&path, &session).is_err());
        assert_eq!(fs::read(&path).unwrap(), original);
        assert_eq!(fs::read_dir(&dir.0).unwrap().count(), 1);
    }
    #[test]
    fn corrupt_and_future_files_are_never_replaced_on_read() {
        let dir = TestDir::new();
        let path = dir.0.join("studio.json");
        for bytes in [b"{bad".as_slice(), b"{\"schema_version\":999}"] {
            fs::write(&path, bytes).unwrap();
            assert!(load(&path).is_err());
            assert_eq!(fs::read(&path).unwrap(), bytes);
        }
    }
}
