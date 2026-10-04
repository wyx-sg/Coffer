//! What the sync alert READS like — the notification. What it LOOKS like is
//! the count beside the menu bar icon, drawn by `tray.rs` from `tray_state.rs`.
//!
//! Split out of `sync_alert` to keep that module within the file-size budget,
//! and the seam is an honest one: that module decides *whether* a human is
//! needed and whether they have already been told, which is a state machine
//! with no opinion about wording. This is the other half, and it has
//! none about when it is used. Every line comes in each interface language
//! the web UI ships; `tray_locale.rs` says which one is current.

use crate::tray_locale::Lang;

/// One line, naming the product: it arrives in Notification Centre beside
/// everything else on the machine.
pub fn notification_title(lang: Lang) -> &'static str {
    match lang {
        Lang::En => "Coffer sync needs you",
        Lang::Zh => "Coffer 同步需要你处理",
    }
}

/// What went wrong, in the terms the user has to act in. Each says what has
/// stopped as well as what happened — "held" means nothing else will converge,
/// and that is the part that cost four days.
pub fn notification_body(status: &str, lang: Lang) -> &'static str {
    match lang {
        Lang::En => english_body(status),
        Lang::Zh => match status {
            "awaiting_confirmation" => {
                "有一轮同步已暂停，等待你确认。在你答复之前，金库不会再收敛。"
            }
            "conflict" => {
                "有一轮同步遇到了无法自动解决的冲突。金库未被改动，同步已停止，直到你解决它。"
            }
            "push_failed" => "有一轮同步已在本地应用，但推送失败。本机的变更还不在远端。",
            "failed" => "上一轮同步运行失败。金库已停止收敛。",
            "awaiting_join" => {
                "这台机器尚未加入同步远端。在你查看并确认加入之前，不会收敛任何内容。"
            }
            _ => "上一轮同步需要你处理后才能继续。",
        },
    }
}

fn english_body(status: &str) -> &'static str {
    match status {
        "awaiting_confirmation" => {
            "A round is held for your confirmation. The vault will not converge \
             again until you answer it."
        }
        "conflict" => {
            "A round hit a conflict nothing could resolve. The vault is \
             untouched and sync is stopped until you resolve it."
        }
        "push_failed" => {
            "A round applied locally but could not push. This machine's \
             changes are not on the remote yet."
        }
        "failed" => "The last round failed to run. The vault has stopped converging.",
        "awaiting_join" => {
            "This machine has not joined the sync remote yet. Nothing converges \
             until you review the join and adopt it."
        }
        // Unreachable through `next_action`, which only raises on the five
        // above; a default keeps a daemon that grew a sixth status from being
        // reported as nothing at all.
        _ => "The last round needs your attention before sync can continue.",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    // The vocabulary lives with the state machine; this module is only asked
    // to have a line for every entry in it.
    use crate::sync_alert::ATTENTION_STATUSES;

    #[test]
    fn every_attention_status_has_its_own_body_and_label() {
        for lang in [Lang::En, Lang::Zh] {
            let mut bodies: Vec<&str> = ATTENTION_STATUSES
                .iter()
                .map(|s| notification_body(s, lang))
                .collect();
            assert!(bodies.iter().all(|b| !b.is_empty()));
            bodies.sort_unstable();
            bodies.dedup();
            assert_eq!(
                bodies.len(),
                ATTENTION_STATUSES.len(),
                "two statuses share a body in {lang:?}"
            );
        }
        assert_ne!(notification_title(Lang::En), notification_title(Lang::Zh));
    }
}
