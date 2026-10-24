**FAIL — preserved first observation, not a product release.**

Source: `db639ffefcb49020b9c0cea08d5ca03b8bfa2cf0`.
[Run 40046411757](https://github.com/thatsmethen/ravelink/actions/runs/40046411757), attempt 1, macOS 15.7.9 ARM64.

- Native runtime stopped with Xrun during the initial gain phase; remaining protocol phases are incomplete. The fault's input/output origin is not recorded distinctly.
- Separate basic HAL writer skipped 764 frames and recorded an overload. Its two readers and restart-silence checks passed, but the overall protocol failed.
- Both jobs completed owned-driver cleanup and verified both cable UIDs absent.
- Original artifacts and thresholds are unchanged. Extra diagnostics can perturb scheduling; no production or uninstrumented timing qualification is claimed.

Original GitHub artifacts, including raw PCM, callback journals, native lifecycle records and custody manifests:

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| original-runtime.zip | 1,318,980 | `305f7fb58d47ed58a0463f34a5d260e649c56545255663df12400ec11a18b6a3` |
| original-hal.zip | 10,535,374 | `5561b48ae602bd1a2da04982882660edff15760cdcaaa054a520e89b0590486d` |

Every archive digest matches the original GitHub artifact digest, and every manifest member was verified before publication. These assets are evidence, not installable product packages.
