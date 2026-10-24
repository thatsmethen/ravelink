fn main() {
    println!("cargo:rerun-if-changed=../../packaging/branding/ravelink.res");
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows")
        && std::env::var("CARGO_CFG_TARGET_ENV").as_deref() == Ok("msvc")
    {
        let resource = std::path::PathBuf::from(std::env::var_os("CARGO_MANIFEST_DIR").unwrap())
            .join("../../packaging/branding/ravelink.res");
        println!(
            "cargo:rustc-link-arg-bin=ravelink-app={}",
            resource
                .canonicalize()
                .expect("ReLink icon resource")
                .display()
        );
    }
}
