//! Entry point for the GUI (project 2).
//!
//! This is the native (desktop) launcher, trimmed from emilk/eframe_template.
//! The original template also has a web/wasm branch here; we removed it so the
//! project stays simple and builds without the extra `trunk` web tooling.

// On Windows release builds this hides the extra console window. No effect on Linux.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() -> eframe::Result {
    // Send `log` output to stderr. Run with `RUST_LOG=debug cargo run -p gui` for more.
    env_logger::init();

    // Window options: starting size and the smallest the user may shrink it to.
    let native_options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([700.0, 400.0])
            .with_min_inner_size([400.0, 250.0]),
        ..Default::default()
    };

    // Open the window and run the event loop. The closure builds our app once,
    // on startup; `cc` (the CreationContext) gives access to any saved state.
    eframe::run_native(
        "yambot gui",
        native_options,
        Box::new(|cc| Ok(Box::new(gui::TemplateApp::new(cc)))),
    )
}
