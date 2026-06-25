//! Library half of the GUI crate.
//!
//! Splitting the app into a `lib.rs` (the app logic) and a `main.rs` (the
//! launcher) mirrors the eframe_template layout. Here we just expose the app
//! type so `main.rs` can construct it.

mod app;
pub use app::TemplateApp;
