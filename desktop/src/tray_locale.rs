//! The language the tray speaks, and the words it says in each.
//!
//! The interface language is the page's choice: the web UI keeps it in the
//! webview's own storage and falls back to the OS language, and the shell has
//! no reach into either. So the page tells the shell — once when it starts and
//! again on every switch — through the `set_ui_language` command, and the tray
//! relabels on the spot (spec desktop-app "Host the UI locally in an
//! application window"). Until the page has spoken, which is the few seconds
//! of a launch before the webview runs its first script, the tray follows the
//! OS language, which is also what the page itself falls back to.
//!
//! The choice is held in memory only: the page re-sends it on every launch,
//! so a copy on disk would be a second record of it that could disagree.

use std::sync::atomic::{AtomicU8, Ordering};

/// The interface languages the web UI ships (`frontend/src/i18n`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Lang {
    En,
    Zh,
}

impl Lang {
    /// Read a BCP 47 tag the way the page does: anything Chinese is `Zh`, and
    /// everything else falls back to English, as `fallbackLng` does there.
    pub fn from_tag(tag: &str) -> Lang {
        if tag.trim().to_ascii_lowercase().starts_with("zh") {
            Lang::Zh
        } else {
            Lang::En
        }
    }

    fn to_u8(self) -> u8 {
        match self {
            Lang::En => 1,
            Lang::Zh => 2,
        }
    }

    fn from_u8(v: u8) -> Option<Lang> {
        match v {
            1 => Some(Lang::En),
            2 => Some(Lang::Zh),
            _ => None,
        }
    }
}

/// The page's choice, once it has made one. `0` means "not told yet".
static CHOSEN: AtomicU8 = AtomicU8::new(0);

/// The language to label the tray in now: the page's choice, or the OS
/// language before the page has spoken.
pub fn current() -> Lang {
    Lang::from_u8(CHOSEN.load(Ordering::Relaxed)).unwrap_or_else(os_lang)
}

/// Record the page's choice. Returns whether it changed what the tray should
/// say, so the caller can skip a relabel that would repaint the same words.
pub fn choose(lang: Lang) -> bool {
    let before = current();
    CHOSEN.store(lang.to_u8(), Ordering::Relaxed);
    before != lang
}

fn os_lang() -> Lang {
    sys_locale::get_locale()
        .map(|tag| Lang::from_tag(&tag))
        .unwrap_or(Lang::En)
}

/// The tray's fixed words in one language. The Sync entry's attention label is
/// built per status in `sync_presentation.rs`.
pub struct TrayText {
    pub open: &'static str,
    pub sync_idle: &'static str,
    pub restart: &'static str,
    pub quit: &'static str,
    pub tooltip: &'static str,
    pub tooltip_attention: &'static str,
}

/// English. "Sync status" claims nothing about the vault's state, so an
/// unconfigured machine is not shown a reassurance it has not earned.
const EN: TrayText = TrayText {
    open: "Open Coffer",
    sync_idle: "Sync status",
    restart: "Restart daemon",
    quit: "Quit Coffer",
    tooltip: "Coffer",
    tooltip_attention: "Coffer — sync needs attention",
};

/// Chinese, in the web UI's own terms (`zh.json`: 同步, 重启守护进程).
const ZH: TrayText = TrayText {
    open: "打开 Coffer",
    sync_idle: "同步状态",
    restart: "重启守护进程",
    quit: "退出 Coffer",
    tooltip: "Coffer",
    tooltip_attention: "Coffer — 同步需要处理",
};

pub fn tray_text(lang: Lang) -> &'static TrayText {
    match lang {
        Lang::En => &EN,
        Lang::Zh => &ZH,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn from_tag_reads_every_chinese_tag_as_chinese() {
        for tag in ["zh", "zh-CN", "zh-Hans-CN", "zh_TW", "ZH-hk", " zh "] {
            assert_eq!(Lang::from_tag(tag), Lang::Zh, "{tag}");
        }
    }

    #[test]
    fn from_tag_falls_back_to_english_like_the_page_does() {
        for tag in ["en", "en-US", "fr-FR", "ja", ""] {
            assert_eq!(Lang::from_tag(tag), Lang::En, "{tag}");
        }
    }

    // acceptance(spec = "desktop-app", scenario = "the tray speaks the interface language")
    #[test]
    fn the_tray_speaks_the_language_the_page_chose() {
        // The only test that touches the process-wide choice, so no other
        // test can observe it mid-flight.
        choose(Lang::Zh);
        assert_eq!(current(), Lang::Zh);
        let zh = tray_text(current());
        assert_eq!(zh.open, "打开 Coffer");
        assert_eq!(zh.sync_idle, "同步状态");
        assert_eq!(zh.restart, "重启守护进程");
        assert_eq!(zh.quit, "退出 Coffer");

        // Switching back relabels, and saying the same thing twice is no change.
        assert!(choose(Lang::En));
        assert!(!choose(Lang::En));
        let en = tray_text(current());
        assert_eq!(en.open, "Open Coffer");
        assert_eq!(en.sync_idle, "Sync status");
        assert_eq!(en.restart, "Restart daemon");
        assert_eq!(en.quit, "Quit Coffer");
    }

    #[test]
    fn every_language_labels_every_item() {
        for lang in [Lang::En, Lang::Zh] {
            let t = tray_text(lang);
            for label in [
                t.open,
                t.sync_idle,
                t.restart,
                t.quit,
                t.tooltip,
                t.tooltip_attention,
            ] {
                assert!(!label.trim().is_empty(), "{lang:?}");
            }
        }
        // Chinese is not English under another name.
        assert_ne!(tray_text(Lang::Zh).restart, tray_text(Lang::En).restart);
    }
}
