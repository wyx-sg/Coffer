//! The presence check the shell runs before it signs anything (spec
//! desktop-app "Release plaintext and approvals only after a presence check in
//! the shell"; design D1 of `add-secret-boundary`).
//!
//! Every operation gets a fresh `LAContext` with policy
//! `deviceOwnerAuthentication` (Touch ID, a watch, or the login password), and
//! the prompt's reason names the operation and its target, so it is the
//! *operating system* that shows the person what they are approving — not a
//! page an agent might have written. There is no reuse window: no context is
//! kept and `touchIDAuthenticationAllowableReuseDuration` is never set, so one
//! approval never covers a second operation.
//!
//! The decisions — which path to take, what the prompt says, what a failure
//! is called — are pure functions here; the Objective-C calls are in
//! `presence_macos.rs`, and every other platform gets a stub that refuses.

use tauri::AppHandle;

/// What a prompt is about. Each variant carries the target the grant will be
/// signed over, so the words and the signature cannot describe two things.
pub enum Subject<'a> {
    Reveal {
        secret_ref: &'a str,
    },
    Approve {
        id: &'a str,
        description: &'a str,
    },
    /// Several approvals at once: each one's description, as the daemon words it.
    ApproveBatch {
        descriptions: &'a [String],
    },
    ExportMasterKey,
    /// Installing the master key whose fingerprint this is.
    ImportMasterKey {
        fingerprint: &'a str,
    },
}

/// The prompt's reason. macOS shows it as "Coffer is trying to <reason>", so
/// it starts with a verb. In a development build it starts with "Development
/// build — ", because there the grant could have been forged by any same-user
/// process and the person deserves to know the check is a courtesy.
pub fn reason(subject: &Subject<'_>, development: bool) -> String {
    let what = match subject {
        Subject::Reveal { secret_ref } => format!("reveal the secret {secret_ref}"),
        Subject::Approve { id, description } => {
            let description = description.trim();
            if description.is_empty() {
                format!("approve request {id}")
            } else {
                format!("approve: {description}")
            }
        }
        Subject::ApproveBatch { descriptions } => batch_reason(descriptions),
        Subject::ExportMasterKey => "export a backup of Coffer's master key".to_owned(),
        Subject::ImportMasterKey { fingerprint } => {
            format!("replace Coffer's master key with the key {fingerprint}")
        }
    };
    if development {
        format!("Development build — {what}")
    } else {
        what
    }
}

/// How many descriptions the operating system's one-line prompt spells out; the
/// rest are counted. The page lists every item before the person starts the
/// check, and the grant is signed over the whole list.
const BATCH_PROMPT_ITEMS: usize = 3;

fn batch_reason(descriptions: &[String]) -> String {
    let shown: Vec<&str> = descriptions
        .iter()
        .take(BATCH_PROMPT_ITEMS)
        .map(|d| d.trim())
        .collect();
    let rest = descriptions.len().saturating_sub(BATCH_PROMPT_ITEMS);
    let mut text = format!(
        "approve {} changes: {}",
        descriptions.len(),
        shown.join("; ")
    );
    if rest > 0 {
        text.push_str(&format!("; and {rest} more listed in the Coffer window"));
    }
    text
}

/// How a check is carried out.
#[derive(Debug, PartialEq, Eq)]
pub enum CheckPath {
    /// The operating system's own prompt.
    LocalAuthentication,
    /// A modal alert in the app window. Development builds only.
    AppConfirmation,
    /// Nothing can confirm a person is present: the operation is refused.
    Refuse,
}

/// A Mac without a password or biometrics cannot run the policy. A production
/// build refuses then; only a development build — where the grant is already
/// forgeable — may fall back to asking in its own window. The flag is the
/// shell's own compile-time mode, never the daemon's answer, so a daemon cannot
/// talk a signed shell down to the weaker check.
pub fn choose_path(local_authentication_available: bool, development_build: bool) -> CheckPath {
    match (local_authentication_available, development_build) {
        (true, _) => CheckPath::LocalAuthentication,
        (false, true) => CheckPath::AppConfirmation,
        (false, false) => CheckPath::Refuse,
    }
}

/// `LAError` codes that mean the person (or the system on their behalf) did
/// not go through with it — reported as a plain "cancelled", which the page
/// treats as nothing having happened.
const LA_CANCEL_CODES: [isize; 3] = [
    -2, /* userCancel */
    -4, /* systemCancel */
    -9, /* appCancel */
];

/// The message a failed check is reported with.
pub fn failure_message(code: isize, description: &str) -> String {
    if LA_CANCEL_CODES.contains(&code) {
        "cancelled".to_owned()
    } else {
        format!("the presence check failed: {description}")
    }
}

/// What the native layer reports.
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
pub enum NativeOutcome {
    Approved,
    /// The policy cannot run on this Mac (no password, no biometrics).
    Unavailable(String),
    Failed {
        code: isize,
        description: String,
    },
}

/// Confirm a person is present for exactly this operation. Blocks until they
/// answer; call it off the main thread. `Ok` only on an explicit approval.
pub fn confirm(
    app: &AppHandle,
    subject: &Subject<'_>,
    daemon_says_development: bool,
) -> Result<(), String> {
    let development_build = crate::master_key::is_development_build();
    // Either side reporting development titles the prompt so; only the
    // shell's own build decides whether the weaker fallback is allowed.
    let text = reason(subject, development_build || daemon_says_development);
    match native::evaluate(&text) {
        NativeOutcome::Approved => Ok(()),
        NativeOutcome::Failed { code, description } => Err(failure_message(code, &description)),
        NativeOutcome::Unavailable(why) => {
            match choose_path(false, development_build) {
                CheckPath::AppConfirmation => {
                    log::warn!("presence: LocalAuthentication unavailable ({why}); asking in the app window");
                    if native::confirm_in_window(app, &text)? {
                        Ok(())
                    } else {
                        Err("cancelled".to_owned())
                    }
                }
                _ => Err(format!(
                "this Mac cannot confirm you are present (set a login password or Touch ID): {why}"
            )),
            }
        }
    }
}

#[cfg(target_os = "macos")]
#[path = "presence_macos.rs"]
mod native;

#[cfg(not(target_os = "macos"))]
mod native {
    use super::NativeOutcome;

    pub fn evaluate(_reason: &str) -> NativeOutcome {
        NativeOutcome::Unavailable("presence checks are only available on macOS".to_owned())
    }

    pub fn confirm_in_window(_app: &tauri::AppHandle, _reason: &str) -> Result<bool, String> {
        Err("presence checks are only available on macOS".to_owned())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // acceptance(spec = "desktop-app", scenario = "every presence prompt names what it approves")
    #[test]
    fn every_prompt_names_the_operation_and_its_target() {
        let reveal = Subject::Reveal {
            secret_ref: "gh/token",
        };
        assert_eq!(reason(&reveal, false), "reveal the secret gh/token");
        assert_eq!(
            reason(&reveal, true),
            "Development build — reveal the secret gh/token"
        );

        let approve = Subject::Approve {
            id: "0123456789abcdef",
            description: "send github/token to MCP server gh",
        };
        assert_eq!(
            reason(&approve, false),
            "approve: send github/token to MCP server gh"
        );
        assert_eq!(
            reason(&approve, true),
            "Development build — approve: send github/token to MCP server gh"
        );
        // No description from the daemon: the id still names the target.
        let bare = Subject::Approve {
            id: "0123456789abcdef",
            description: "  ",
        };
        assert_eq!(reason(&bare, false), "approve request 0123456789abcdef");

        // A batch names the first few and counts the rest.
        let many: Vec<String> = (1..=5).map(|n| format!("send s to server {n}")).collect();
        let batch = reason(
            &Subject::ApproveBatch {
                descriptions: &many,
            },
            false,
        );
        assert!(
            batch.starts_with("approve 5 changes: send s to server 1; "),
            "{batch}"
        );
        assert!(batch.contains("server 3"), "{batch}");
        assert!(!batch.contains("server 4"), "{batch}");
        assert!(
            batch.ends_with("and 2 more listed in the Coffer window"),
            "{batch}"
        );

        let export = reason(&Subject::ExportMasterKey, true);
        assert!(export.starts_with("Development build — "), "{export}");
        assert!(export.contains("master key"), "{export}");

        let import = reason(
            &Subject::ImportMasterKey {
                fingerprint: "f11ef11ef11e",
            },
            false,
        );
        assert_eq!(
            import,
            "replace Coffer's master key with the key f11ef11ef11e"
        );
    }

    #[test]
    fn only_a_development_build_falls_back_to_asking_in_the_window() {
        assert_eq!(choose_path(true, false), CheckPath::LocalAuthentication);
        assert_eq!(choose_path(true, true), CheckPath::LocalAuthentication);
        assert_eq!(choose_path(false, true), CheckPath::AppConfirmation);
        assert_eq!(choose_path(false, false), CheckPath::Refuse);
    }

    #[test]
    fn a_cancelled_prompt_is_called_cancelled() {
        for code in [-2, -4, -9] {
            assert_eq!(failure_message(code, "whatever"), "cancelled");
        }
        let failed = failure_message(-1, "Authentication failed.");
        assert!(failed.contains("Authentication failed."), "{failed}");
    }
}
