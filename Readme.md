# Firmware Rust Patcher

This repository contains a tool for patching firmware with new Rust UEFI images.

It is not meant to be a general-purpose patching tool. It is meant to allow a number of known compatible platform
firmware images to be patched with a new Rust DXE Core UEFI image. It makes assumptions about the firmware image
to reduce complexity and dependencies.

This has currently only been tested on Windows.

## Next Steps

1. Verify support on Linux

## Usage

Run the firmare patcher Python script. See `--help` for options.

   ```sh
   python patch.py --help
   ```

Generally, you just need to give the config file for the platform and the location of the Rust DXE Core EFI image.

```sh
python patch.py --config Configs/QemuQ35.json -i "C:\src\patina-dxe-core-qemu\target\x86_64-unknown-uefi\debug\qemu_q35_dxe_core.efi"
```

The command-line arguments override equivalent values in the config file. It is recommended to also specify the config
file for the platform target and then override what you'd like.

Paths can be absolute or relative to the repo root.

## Tips

1. You can create your own local config files and add them to your `.git/info/exclude` file to prevent them from being
   tracked by git. You can customize the config file to include paths for your system so the config file is the only
   command-line argument you need to provide.
2. You can add the `"INPUT"` member to the config file to avoid having to pass it in as a command-line argument.
   Example:

   ```json
    "Paths": {
      "FvLayout": "./Reference/Layouts/qemu_q35.inf",
      "ReferenceFw": "C:\\src\\patina-qemu\\Build\\QemuQ35Pkg\\DEBUG_VS2022\\FV\\QEMUQ35_CODE.ref.fd",
      "Output": "C:\\src\\patina-qemu\\Build\\QemuQ35Pkg\\DEBUG_VS2022\\FV\\QEMUQ35_CODE.fd",
      "Input": "C:\\src\\patina-dxe-core-qemu\\target\\x86_64-unknown-uefi\\debug\\qemu_q35_dxe_core.efi"
    }
   ```

## Patching QEMU Q35 Example

This shows how the tool can be used in a flow to build the Rust DXE Core EFI image, patch a QEMU Q35 firmware ROM,
and boot within seconds (depending on Rust DXE Core build time).

![QEMU Q35 Automation Example](Docs/Images/qemu_q35_rustdxecore_patch.gif)
