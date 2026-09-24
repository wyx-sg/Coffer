//! What the alert LOOKS like and READS like — the words that go with it, and
//! the mark painted onto the app's own icon.
//!
//! Split out of `sync_alert` to keep that module within the file-size budget,
//! and the seam is an honest one: that module decides *whether* a human is
//! needed and whether they have already been told, which is a state machine
//! with no opinion about wording or pixels. This is the other half, and it has
//! none about when it is used.

/// The alert dot: a red disc inside a white ring, so it reads against both a
/// light and a dark menu bar.
const BADGE_FILL: [u8; 4] = [0xE5, 0x48, 0x4D, 0xFF];
const BADGE_RING: [u8; 4] = [0xFF, 0xFF, 0xFF, 0xFF];

/// Paint the alert dot into the bottom-right of a straight-RGBA image.
///
/// Badging the icon the app already has beats shipping a second `.png`: the two
/// cannot drift, and the mark lands in the same place whatever the base icon
/// becomes. A buffer whose length does not match its declared size is returned
/// untouched — a marked icon is worth having, a panicked tray thread is not.
pub fn badge_rgba(rgba: &[u8], width: u32, height: u32) -> Vec<u8> {
    let expected = (width as usize) * (height as usize) * 4;
    if rgba.len() != expected || width == 0 || height == 0 {
        return rgba.to_vec();
    }
    let mut out = rgba.to_vec();

    // Three-sixteenths of the shorter side, floored at 2px: big enough to see
    // in a 16pt menu bar, small enough to leave the icon recognisable.
    let radius = ((width.min(height) * 3) / 16).max(2) as i64;
    let ring = radius + (radius / 4).max(1);
    let cx = width as i64 - ring - 1;
    let cy = height as i64 - ring - 1;

    for y in 0..height as i64 {
        for x in 0..width as i64 {
            let d2 = (x - cx) * (x - cx) + (y - cy) * (y - cy);
            let colour = if d2 <= radius * radius {
                BADGE_FILL
            } else if d2 <= ring * ring {
                BADGE_RING
            } else {
                continue;
            };
            let i = ((y as usize) * (width as usize) + (x as usize)) * 4;
            out[i..i + 4].copy_from_slice(&colour);
        }
    }
    out
}

/// One line, naming the product: it arrives in Notification Centre beside
/// everything else on the machine.
pub const NOTIFICATION_TITLE: &str = "Coffer sync needs you";

/// What went wrong, in the terms the user has to act in. Each says what has
/// stopped as well as what happened — "held" means nothing else will converge,
/// and that is the part that cost four days.
pub fn notification_body(status: &str) -> &'static str {
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

/// The tray entry's label while a condition is outstanding. Short — it sits in
/// a menu — and it names the condition, so the tray answers "which problem"
/// without the window being opened.
pub fn tray_label(status: &str) -> String {
    let reason = match status {
        "awaiting_confirmation" => "held for confirmation",
        "conflict" => "conflict",
        "push_failed" => "push failed",
        "failed" => "run failed",
        "awaiting_join" => "not joined yet",
        _ => status,
    };
    format!("Sync needs attention — {reason}")
}

#[cfg(test)]
mod tests {
    use super::*;
    // The vocabulary lives with the state machine; this module is only asked
    // to have a line for every entry in it.
    use crate::sync_alert::ATTENTION_STATUSES;

    #[test]
    fn every_attention_status_has_its_own_body_and_label() {
        let mut bodies: Vec<&str> = ATTENTION_STATUSES
            .iter()
            .map(|s| notification_body(s))
            .collect();
        assert!(bodies.iter().all(|b| !b.is_empty()));
        bodies.sort_unstable();
        bodies.dedup();
        assert_eq!(
            bodies.len(),
            ATTENTION_STATUSES.len(),
            "two statuses share a body"
        );

        for status in ATTENTION_STATUSES {
            let label = tray_label(status);
            assert!(label.starts_with("Sync needs attention — "), "{label}");
            // The raw enum name never reaches the menu.
            assert!(!label.contains('_'), "{label}");
        }
    }

    #[test]
    fn badge_rgba_paints_the_dot_in_the_bottom_right() {
        let base = vec![0x11u8; 32 * 32 * 4];
        let marked = badge_rgba(&base, 32, 32);
        assert_eq!(marked.len(), base.len());
        // Top-left is as far from the badge as a pixel gets: untouched.
        assert_eq!(&marked[0..4], &[0x11, 0x11, 0x11, 0x11]);
        // radius = 32*3/16 = 6, ring = 6 + 1 = 7, centre = (24, 24).
        let at = |x: usize, y: usize| &marked[(y * 32 + x) * 4..(y * 32 + x) * 4 + 4];
        assert_eq!(at(24, 24), BADGE_FILL, "centre should be the alert fill");
        assert_eq!(at(24, 31), BADGE_RING, "the ring should surround the fill");
    }

    #[test]
    fn badge_rgba_never_writes_outside_the_buffer_it_was_given() {
        // Declared 32x32 but four pixels long — returned, not panicked on.
        let short = vec![0u8; 16];
        assert_eq!(badge_rgba(&short, 32, 32), short);
        assert_eq!(badge_rgba(&[], 0, 0), Vec::<u8>::new());
        // A 4x4 icon: the radius floors at 2 and every write stays in bounds.
        assert_eq!(badge_rgba(&[0u8; 64], 4, 4).len(), 64);
    }
}
