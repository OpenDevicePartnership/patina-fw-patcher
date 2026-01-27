# @file patch.py
#
# Patches a reference FW image with a new Rust DXE Core.
#
# This script is meant to be focused and fast for patching specific reference
# firmware images with a new Rust DXE Core. It is not meant to be a general
# purpose firmware patching tool.
#
# Copyright (c) Microsoft Corporation. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
##

import argparse
import logging
import os
import sys
import timeit
import uuid
import json
from pathlib import Path, PurePath
from typing import Dict

PROGRAM_NAME = "Rust Firmware Patcher"

# Spec-defined GUID for EFI Filesystem 2.
_EFI_FILESYSTEM_2_GUID = "8c8ce578-8a3d-4f1c-9935-896185c32dd3"

# GUID for the Rust DXE Core FFS file. This GUID is currently required for all
# Rust DXE Core FFS files.
_RUST_DXE_CORE_DEFAULT_FFS_GUID = "23c9322f-2af2-476a-bc4c-26bc88266c71"

# GUID that is used to find the FFS FV if another is not given. This is the
# GUID value used for the Rust DXE Core FV in current Intel platforms firmware.
_RUST_DXE_CORE_DEFAULT_FFS_FV_GUID = "71dad237-900f-4ea8-8dfd-93f8f8c704df"

_SCRIPT_DIR = Path(__file__).parent


class _QuietFilter(logging.Filter):
    """A logging filter that temporarily suppresses message output."""

    def __init__(self, quiet: bool = False):
        """Class constructor method.

        Args:
            quiet (bool, optional): Indicates if messages are currently being
            printed (False) or not (True). Defaults to False.
        """

        self._quiet = quiet

    def filter(self, record: logging.LogRecord) -> bool:
        """Quiet filter method.

        Args:
            record (logging.LogRecord): A log record object that the filter is
            applied to.

        Returns:
            bool: True if messages are being suppressed. Otherwise, False.
        """
        return not self._quiet


def _guid_str_to_hex_val_str(guid_str: str) -> str:
    """Converts a GUID string to a hex value string.

    Args:
        guid_str (str): A GUID string.

    Returns:
        str: A hex value string.
    """
    return " ".join(f"{byte:02X}" for byte in uuid.UUID(guid_str).bytes_le)


def _parse_args() -> argparse.Namespace:
    """Parses the command line arguments."""
    from argparse import RawTextHelpFormatter

    def _check_file_path(file_path: str) -> bool:
        """Returns the absolute path if the path is a file."

        Args:
            file_path (str): A file path.

        Raises:
            FileExistsError: The path is not a valid file.

        Returns:
            bool: True if the path is a valid file else False.
        """
        abs_file_path = os.path.abspath(file_path)
        if os.path.isfile(file_path):
            return abs_file_path
        else:
            raise FileExistsError(file_path)

    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description=("Patches a reference FW image with a new Rust DXE " "Core."),
        formatter_class=RawTextHelpFormatter,
    )

    io_conf_group = parser.add_argument_group("Configuration")
    io_opt_group = parser.add_argument_group("Optional input and output")

    io_conf_group.add_argument(
        "-c",
        "--ref-conf-file-path",
        type=_check_file_path,
        default="Configs/Intel.json",
        help="Path to a reference config file.\n\n"
        "If a config file is given, -o, and -r "
        "are optional.\n\nIf given, their values "
        "will override those in the\nconfig "
        "file.\n"
        "(default: Configs/Intel.json)\n\n",
    )
    io_conf_group.add_argument(
        "-i",
        "--input-dxe-core-efi-path",
        type=_check_file_path,
        help="Path to the new DXE Core EFI file.\n\n",
    )
    io_conf_group.add_argument(
        "-r",
        "--ref-fw-path",
        type=_check_file_path,
        help="Path to the reference FW image to patch.\n\n",
    )
    io_conf_group.add_argument(
        "-o",
        "--output-file-path",
        help="Output file path.\n" "(default: PATCHED_ROM.bin)\n\n",
    )
    io_opt_group.add_argument(
        "-l",
        "--log-file",
        nargs="?",
        default=None,
        const="rust_fw_patcher.log",
        help="File path for log output.\n"
        "(default: if the flag is given with no "
        "file path then a file called\n"
        "rust_fw_patcher.log is created and used "
        "in the current directory)\n\n",
    )
    io_opt_group.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Disables console output.\n" "(default: console output is enabled)\n\n",
    )

    args = parser.parse_args()

    if not args.ref_conf_file_path:
        if not (
            args.input_dxe_core_efi_path and args.ref_fw_path and args.output_file_path
        ):
            parser.error("Arguments -i, -r, and -o are required unless -c is provided.")

    return args


def _patch_ref_binary(config: Dict[str, Dict]):
    """Patches a reference binary with the new Rust DXE Core.

    Args:
        config (Dict[str, Dict]): Configuration settings.
    Raises:
        ValueError: A given configuration settings is invalid.
    """
    import shutil
    import subprocess

    # Check if a reference FW image is compressed (to save space in the repo).
    if config["Paths"]["ReferenceFw"].suffix == ".lzma":
        decompressed_file = (
            config["Paths"]["BuildDir"] / config["Paths"]["ReferenceFw"].name
        ).with_suffix(".decompressed")

        logging.info(
            f"Decompressing reference image {config['Paths']['ReferenceFw']}..."
        )

        decompression_start = timeit.default_timer()
        try:
            result = subprocess.run(
                [
                    _SCRIPT_DIR / "Executables" / "LzmaCompress",
                    "-d",
                    config["Paths"]["ReferenceFw"],
                    "-o",
                    decompressed_file,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"\n\nFailed to run command: LzmaCompress\n\n{e.stdout}\n"
            ) from e
        decompression_end = timeit.default_timer()
        logging.debug(f"  Output = {result.stdout}")
        if result.returncode != 0:
            if decompressed_file.exists():
                decompressed_file.unlink()
            raise ValueError(f"Failed to decompress {config['Paths']['ReferenceFw']}\n")
        logging.info(f"  - In {decompression_end - decompression_start:.2f} seconds!\n")
        config["Paths"]["ReferenceFw"] = decompressed_file

    logging.info(f"Patching reference image {config['Paths']['ReferenceFw']}...")
    shutil.copyfile(config["Paths"]["ReferenceFw"], config["Paths"]["Output"])

    with open(config["Paths"]["Output"], "r+b") as out_bin:
        _OFFSET_TO_SIZE_FROM_GUID = 20
        _LENGTH_OF_SIZE = 3
        _OFFSET_TO_STATE_FROM_GUID = 23

        # Find the offset of the FFS file. Search backward since the file is
        # assumed to be at the end of the binary (right now).
        out_bin_data = out_bin.read()

        patch_cnt = 0
        offset = len(out_bin_data)
        while offset != -1:
            offset = out_bin_data.rfind(
                bytes.fromhex(_guid_str_to_hex_val_str(config["DxeCore"]["FfsGuid"])),
                0,
                offset,
            )
            original_state = out_bin_data[offset + _OFFSET_TO_STATE_FROM_GUID]

            if offset == -1:
                break
            patch_cnt += 1

            old_ffs_size = int.from_bytes(
                out_bin_data[
                    offset
                    + _OFFSET_TO_SIZE_FROM_GUID : offset
                    + _OFFSET_TO_SIZE_FROM_GUID
                    + _LENGTH_OF_SIZE
                ],
                byteorder="little",
            )
            logging.debug(f"Original Rust DXE Core FV FFS size: {old_ffs_size}")

            # Open the newly generated FFS file
            if patch_cnt == 1:
                with open(config["Paths"]["GeneratedFfs"], "rb") as gen_ffs:
                    gen_ffs_data = gen_ffs.read()

            if not gen_ffs_data:
                raise ValueError(
                    "Generated FFS data is empty, cannot patch the binary."
                )

            logging.info(f"Patching in new Rust DXE Core at 0x{offset:X}")

            new_ffs_size = len(gen_ffs_data)
            logging.debug(f"New Rust DXE Core FV FFS size: {new_ffs_size}")

            if new_ffs_size > old_ffs_size:
                raise ValueError(
                    f"\nPatch Failed: Rust DXE Core size mismatch:\n"
                    f"  - New Rust DXE Core FFS size: {new_ffs_size}\n"
                    f"  - Existing Rust DXE Core FFS size: {old_ffs_size}\n"
                    f"Cause:\n"
                    f"  - The Rust DXE Core embedded in the reference FD by stuart_build\n"
                    f"    (from the DXECORE.QEMU external dependency) is smaller than the\n"
                    f"    Rust DXE Core built locally by the build_and_run_rust_binary script.\n"
                    f"Resolution:\n"
                    f"  - Override the DXECORE.QEMU external dependency with the locally built version.\n"
                    f"  - Rerun stuart_build and then execute the build_and_run_rust_binary script again.\n"
                )

            out_bin.seek(offset)
            out_bin.write(gen_ffs_data)

            if new_ffs_size < old_ffs_size:
                logging.debug(
                    f"Zeroing out remainder of the old FFS file: {old_ffs_size - new_ffs_size} bytes\n"
                )
                out_bin.seek(offset + new_ffs_size)
                out_bin.write(b"\xff" * (old_ffs_size - new_ffs_size))

            out_bin.seek(offset + _OFFSET_TO_STATE_FROM_GUID)
            out_bin.write(bytes([original_state]))

        if patch_cnt == 0:
            raise ValueError(
                "Could not find an existing Rust DXE Core FFS "
                f"in {config['Paths']['ReferenceFw']} with GUID "
                f"{{{config['DxeCore']['FfsGuid']}}}"
            )


def _parse_config(args: argparse.Namespace, conf_path: PurePath = None) -> Dict:
    """Parses the given configuration file and initializes configuration
    settings.

    Args:
        args (argparse.Namespace): The argument parser.
        conf_path (PurePath, optional): Configuration path. Defaults to None.

    Raises:
        ValueError: If a required file path is not given either in the config
                    file or or as a command line argument.
        FileNotFoundError: If a file path was given but the file does not exist.

    Returns:
        Dict: A dictionary of configuration settings.
    """

    config = {}

    if conf_path:
        with open(conf_path, "r") as conf_file:
            config = json.load(conf_file)

        config["Name"] = conf_path.stem
        logging.info(f"Loading config file for {config['Name']}:\n" f"  {conf_path}\n")
    else:
        config["Name"] = "Intel"

    if args.ref_fw_path:
        config["Paths"]["ReferenceFw"] = args.ref_fw_path
    if args.input_dxe_core_efi_path:
        config["Paths"]["Input"] = args.input_dxe_core_efi_path
    if args.output_file_path:
        config["Paths"]["Output"] = args.output_file_path

    if "DxeCore" not in config:
        config["DxeCore"] = {}
    if "FfsGuid" not in config["DxeCore"]:
        config["DxeCore"]["FfsGuid"] = _RUST_DXE_CORE_DEFAULT_FFS_FV_GUID

    if "Input" not in config["Paths"]:
        raise ValueError("An input file path is required.")

    config["Paths"]["BuildDir"] = _SCRIPT_DIR / "Build" / config["Name"]

    for path in config["Paths"]:
        if not config["Paths"][path]:
            raise ValueError(f'A "{path}" file path is required.')
        config["Paths"][path] = Path(config["Paths"][path])
        if path == "Input":
            if config["Paths"]["Input"].suffix != ".efi":
                logging.warning("**The input file does not have a .efi extension.**\n")
            if not config["Paths"][path].is_absolute():
                config["Paths"][path] = _SCRIPT_DIR / config["Paths"][path]
        if (
            not config["Paths"][path].exists()
            and path != "Output"
            and path != "BuildDir"
        ):
            raise FileNotFoundError(
                f'The given "{path}" file '
                f"({str(config['Paths'][path])}) does "
                "not exist."
            )

    if args.log_file:
        config["Paths"]["Log"] = Path(args.log_file)

    return config


def _generate_new_ffs(config: Dict) -> None:
    """Generates a new Rust DXE Core FFS file.

    Args:
        config (Dict): Configuration settings.
    """
    import shutil
    import subprocess

    logging.info("Generating new Rust DXE Core FFS:\n")

    target_dir = config["Paths"]["BuildDir"]
    target_dir.mkdir(parents=True, exist_ok=True)

    build_fv_layout = target_dir / config["Paths"]["FvLayout"].name
    shutil.copyfile(config["Paths"]["FvLayout"], build_fv_layout)

    with open(build_fv_layout, "r+") as build_fv_layout_file:
        build_fv_layout_data = build_fv_layout_file.read()
        build_fv_layout_data = build_fv_layout_data.replace(
            "TO_PATCH", str(target_dir / "DxeCore.ffs")
        )
        build_fv_layout_file.seek(0)
        build_fv_layout_file.write(build_fv_layout_data)

    commands = [
        (
            "GenSec",
            [
                "-s",
                "EFI_SECTION_PE32",
                "-o",
                str(target_dir / "DxeCore.pe32"),
                config["Paths"]["Input"],
            ],
        ),
        (
            "GenFfs",
            [
                "-t",
                "EFI_FV_FILETYPE_DXE_CORE",
                "-g",
                _RUST_DXE_CORE_DEFAULT_FFS_GUID,
                "-i",
                str(target_dir / "DxeCore.pe32"),
                "-oi",
                "Reference/Binaries/RustDxeCore.ui",
                "-o",
                str(target_dir / "DxeCore.ffs"),
            ],
        ),
        (
            "GenFv",
            [
                "-F",
                "FALSE",
                "-g",
                _EFI_FILESYSTEM_2_GUID,
                "-i",
                str(build_fv_layout),
                "-o",
                str(target_dir / "DxeCoreUncompressed.fv"),
            ],
        ),
        (
            "GenSec",
            [
                "-s",
                "EFI_SECTION_FIRMWARE_VOLUME_IMAGE",
                "-o",
                str(target_dir / "DxeCoreUncompressed.fv.sec"),
                str(target_dir / "DxeCoreUncompressed.fv"),
            ],
        ),
        (
            "GenSec",
            [
                "--sectionalign",
                "16",
                "-o",
                str(target_dir / "DxeCoreUncompressed.fv.sec.guided.dummy"),
                str(target_dir / "DxeCoreUncompressed.fv.sec"),
            ],
        ),
        (
            "LzmaCompress",
            [
                "-e",
                str(target_dir / "DxeCoreUncompressed.fv.sec.guided.dummy"),
                "-o",
                str(target_dir / "DxeCoreCompressed.fv.bin"),
            ],
        ),
        (
            "GenSec",
            [
                "-s",
                "EFI_SECTION_GUID_DEFINED",
                "-g",
                config["DxeCore"]["CompressionGuid"],
                "-r",
                "PROCESSING_REQUIRED",
                "-o",
                str(target_dir / "DxeCoreCompressed.fv.guided.sec"),
                str(target_dir / "DxeCoreCompressed.fv.bin"),
            ],
        ),
        (
            "GenFfs",
            [
                "-t",
                "EFI_FV_FILETYPE_FIRMWARE_VOLUME_IMAGE",
                "-g",
                config["DxeCore"]["FfsGuid"],
                "-i",
                str(target_dir / "DxeCoreCompressed.fv.guided.sec"),
                "-o",
                str(target_dir / "DxeCoreCompressedFv.ffs"),
            ],
        ),
    ]

    for step, command in enumerate(commands, start=1):
        step_text = f"[{step}]."
        logging.info(f'  {step_text} Running "{command[0]}"...')
        logging.debug(f"  {' ' * len(step_text)} Command = {command}\n")
        exe_name = f"{command[0]}.exe" if os.name == "nt" else command[0]

        try:
            result = subprocess.run(
                [_SCRIPT_DIR / "Executables" / exe_name] + command[1],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f'\n\nFailed to run command: {"".join(str(command))}\n\n{e.stdout}\n'
            ) from e

        log_msg = f"  {' ' * len(step_text)} Output = " f"{str(result.stdout).rstrip()}"

        if result.stdout:
            logging.info(log_msg)
        else:
            logging.debug(log_msg)

    logging.info("")

    config["Paths"]["GeneratedFfs"] = str(target_dir / "DxeCoreCompressedFv.ffs")


def _main():
    """Main execution flow."""

    def _quiet_print(*args, **kwargs):
        """Replaces print when quiet is requested to prevent printing messages."""
        pass

    import builtins

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    stdout_logger_handler = logging.StreamHandler(sys.stdout)
    stdout_logger_handler.set_name("stdout_logger_handler")
    stdout_logger_handler.setLevel(logging.INFO)
    stdout_logger_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(stdout_logger_handler)

    args = None
    try:
        args = _parse_args()
    except FileExistsError as e:
        logging.error(f"The given file path does not exist: {e}")
        sys.exit(1)

    if args.quiet:
        builtins.print = _quiet_print
    stdout_logger_handler.addFilter(_QuietFilter(args.quiet))

    if args.log_file:
        file_logger_handler = logging.FileHandler(
            filename=args.log_file, mode="w", encoding="utf-8"
        )

        file_logger_handler.setLevel(logging.DEBUG)
        file_logger_formatter = logging.Formatter("%(levelname)-8s %(message)s")

        file_logger_handler.setFormatter(file_logger_formatter)
        root_logger.addHandler(file_logger_handler)

    logging.info(PROGRAM_NAME + "\n")

    start_time = timeit.default_timer()

    try:
        config = _parse_config(args, PurePath(args.ref_conf_file_path))
        _generate_new_ffs(config)
        _patch_ref_binary(config)
    except ValueError as e:
        logging.error(e)
        sys.exit(1)

    end_time = timeit.default_timer()
    total_duration = end_time - start_time

    logging.info(f"Patched file at {config['Paths']['Output']}\n")
    logging.info(f"Patching complete in {total_duration:.2f} seconds!")


if __name__ == "__main__":
    _main()
