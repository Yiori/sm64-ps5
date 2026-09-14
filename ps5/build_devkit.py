#!/usr/bin/env python3
import os
import sys
import glob
import shutil
import subprocess
import concurrent.futures

PROSPERO_SDK = r"D:\SDK\Sony\Prospero SDKs\13.000"
PROSPERO_TOOLS = r"D:\SDK\Sony\Prospero\Tools"
CC = os.path.join(PROSPERO_SDK, "host_tools", "bin", "prospero-clang.exe")
PUB_CMD = os.path.join(PROSPERO_TOOLS, "Publishing Tools", "bin", "prospero-pub-cmd.exe")
LIBC_PRX = os.path.join(PROSPERO_SDK, "target", "sce_module", "libc.prx")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HERE = os.path.join(ROOT, "ps5")
OUT = os.path.join(HERE, "out")

TITLE_ID = os.environ.get("TITLE_ID", "PPSA64064")
TITLE_NAME = os.environ.get("TITLE_NAME", "SM64 PS5")

DEFS = [
    "-D_LANGUAGE_C", "-DVERSION_US=1", "-DF3DEX_GBI_2E=1",
    "-DNON_MATCHING=1", "-DAVOID_UB=1", "-DNO_SEGMENTED_MEMORY",
    "-DUSE_SYSTEM_MALLOC", "-DWIDESCREEN", "-DSM64_PS5_REFLECTIONS",
    "-DSM64_PS5_HD_TEXTURES", "-DSM64_PS5_LANGUAGE", "-DENABLE_RUMBLE=1",
]

INCS = [
    f"-I{ROOT}/include",
    f"-I{ROOT}/src",
    f"-I{ROOT}/src/pc",
    f"-I{ROOT}",
    f"-I{ROOT}/build/us_pc",
    f"-I{ROOT}/build/us_pc/include",
    f"-I{HERE}/lang",
    f"-I{OUT}/lang",
]

ENGINE_FLAGS = [
    "-g", "-O2", "-fno-strict-aliasing", "-fwrapv", "-Wno-everything",
    *DEFS, *INCS,
    '-DSM64_SAVE_FILE_PATH="/app0/data/sm64_ps5/saves/sm64_save_file.bin"',
]

def run_cmd(cmd, check=True):
    res = subprocess.run(cmd, check=check, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"FAILED: {cmd}")
        print("STDOUT:", res.stdout)
        print("STDERR:", res.stderr)
        if check:
            sys.exit(res.returncode)
    return res

def compile_c(src, obj, flags):
    os.makedirs(os.path.dirname(obj), exist_ok=True)
    cmd = [CC, *flags, "-c", src, "-o", obj]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error compiling {src}:")
        print(res.stderr)
        return False
    return True

def main():
    os.makedirs(os.path.join(OUT, "obj", "engine"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "obj", "ps5"), exist_ok=True)

    print(">>> 1. Compiling engine sources...")
    with open(os.path.join(HERE, "engine_sources.txt")) as f:
        engine_sources = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    tasks = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 8) as executor:
        for src in engine_sources:
            full_src = os.path.join(ROOT, src.replace("/", os.sep))
            obj_name = src.replace("/", "_") + ".o"
            obj_path = os.path.join(OUT, "obj", "engine", obj_name)
            tasks.append(executor.submit(compile_c, full_src, obj_path, ENGINE_FLAGS))
        
        for task in concurrent.futures.as_completed(tasks):
            if not task.result():
                print("Aborting due to compilation error in engine.")
                sys.exit(1)
    print(f"Compiled {len(engine_sources)} engine sources.")

    print(">>> 2. Compiling language module...")
    lang_sources = [
        os.path.join(HERE, "lang", "ps5_lang.c"),
        os.path.join(HERE, "lang", "translation_es.c"),
        os.path.join(OUT, "lang", "strings_es.c"),
    ]
    for src in lang_sources:
        obj = os.path.join(OUT, "obj", "ps5", os.path.splitext(os.path.basename(src))[0] + ".o")
        if not compile_c(src, obj, ENGINE_FLAGS):
            sys.exit(1)

    print(">>> 3. Compiling glue...")
    glue_tasks = [
        (
            os.path.join(HERE, "glue", "controller_entry_point_ps5.c"),
            os.path.join(OUT, "obj", "engine", "controller_entry_point_ps5.o"),
            ["-O2", "-Wno-everything", *DEFS, *INCS, f"-I{ROOT}/src/pc/controller"]
        ),
        (
            os.path.join(HERE, "glue", "libc_shims.c"),
            os.path.join(OUT, "obj", "ps5", "libc_shims.o"),
            ["-O2", "-fno-builtin"]
        ),
        (
            os.path.join(HERE, "glue", "rumble_ps5.c"),
            os.path.join(OUT, "obj", "ps5", "rumble_ps5.o"),
            [*ENGINE_FLAGS, f"-I{HERE}"]
        ),
        (
            os.path.join(ROOT, "src", "pc", "gfx", "gfx_cc.c"),
            os.path.join(OUT, "obj", "ps5", "gfx_cc.o"),
            ["-O2", "-Wno-everything"]
        ),
        (
            os.path.join(ROOT, "src", "pc", "audio", "audio_null.c"),
            os.path.join(OUT, "obj", "ps5", "audio_null.o"),
            ["-O2", "-Wno-everything", *DEFS, *INCS]
        )
    ]
    for src, obj, flags in glue_tasks:
        if not compile_c(src, obj, flags):
            sys.exit(1)

    print(">>> 4. Compiling PS5 layer...")
    layer_files = [
        "main_ps5", "menu_ps5", "hd_textures", "asset_loader", "sha1",
        "ps5gpu", "gfx_agc", "gfx_ps5", "controller_ps5", "audio_ps5"
    ]
    ps5_flags = [
        "-O2", "-Wall", "-Wno-unused-function", "-Wno-sign-compare", "-Wno-missing-field-initializers",
        *DEFS, "-DENABLE_RUMBLE=1", f"-I{HERE}", *INCS,
        '-DSM64_SAVE_FILE_PATH="/app0/data/sm64_ps5/saves/sm64_save_file.bin"',
    ]
    for f in layer_files:
        src = os.path.join(HERE, f"{f}.c")
        obj = os.path.join(OUT, "obj", "ps5", f"{f}.o")
        if not compile_c(src, obj, ps5_flags):
            sys.exit(1)

    print(">>> 5. Linking sm64_ps5.elf with official Prospero SDK...")
    elf_out = os.path.join(OUT, "sm64_ps5.elf")
    if os.path.exists(elf_out):
        os.remove(elf_out)

    engine_objs = glob.glob(os.path.join(OUT, "obj", "engine", "*.o"))
    ps5_objs = glob.glob(os.path.join(OUT, "obj", "ps5", "*.o"))
    all_objs = ps5_objs + engine_objs

    # Response file to avoid command line length limits on Windows
    rsp_path = os.path.join(OUT, "link_objs.rsp")
    with open(rsp_path, "w") as rf:
        for o in all_objs:
            rf.write(f'"{o.replace(os.sep, "/")}"\n')

    link_cmd = [
        CC,
        f"@{rsp_path}",
        "-o", elf_out,
        "-lkernel_stub_weak",
        "-lSceVideoOut_stub_weak",
        "-lScePad_stub_weak",
        "-lSceAudioOut_stub_weak",
        "-lSceUserService_stub_weak",
        "-lSceSystemService_stub_weak",
        "-lSceAgcDriver_stub_weak",
        "-lSceAgc_stub_weak",
        "-lSceAgcCore",
        "-lSceAgcGpuAddress",
    ]
    print(f"Linking {len(all_objs)} object files...")
    run_cmd(link_cmd)
    print(f"Successfully linked: {elf_out} ({os.path.getsize(elf_out)} bytes)")

    print(">>> 6. Asset stripping & HD index...")
    stripped_elf = os.path.join(OUT, "sm64_ps5_stripped.elf")
    assets_map = os.path.join(OUT, "sm64_assets.map")
    hd_idx = os.path.join(OUT, "sm64_hd_textures.idx")
    baserom = os.path.join(ROOT, "baserom.us.z64")
    assets_json = os.path.join(ROOT, "assets.json")

    run_cmd([sys.executable, os.path.join(HERE, "asset_tools", "asset_strip.py"),
             elf_out, baserom, assets_json, stripped_elf, assets_map])
    print(f"Asset strip complete: {stripped_elf}")

    run_cmd([sys.executable, os.path.join(HERE, "hd_tools", "hd_index.py"),
             baserom, assets_json, os.path.join(ROOT, "build", "us_pc", "bin"), hd_idx])
    print(f"HD index complete: {hd_idx}")

    print(">>> 7. Packaging title directory for DevKit...")
    pkg_dir = os.path.join(OUT, TITLE_ID)
    if os.path.exists(pkg_dir):
        shutil.rmtree(pkg_dir)
    os.makedirs(os.path.join(pkg_dir, "sce_sys"), exist_ok=True)
    os.makedirs(os.path.join(pkg_dir, "sce_module"), exist_ok=True)
    os.makedirs(os.path.join(pkg_dir, "data", "sm64_ps5", "saves"), exist_ok=True)

    # In DevKit mode, use the full self-contained ELF with all assets and debug symbols built-in
    shutil.copy2(elf_out, os.path.join(pkg_dir, "eboot.bin"))
    # (Asset strip is for homebrew distribution; devkit uses self-contained ELF so no runtime patch is needed)
    # shutil.copy2(assets_map, os.path.join(pkg_dir, "sm64_assets.map"))
    shutil.copy2(hd_idx, os.path.join(pkg_dir, "sm64_hd_textures.idx"))
    shutil.copy2(os.path.join(HERE, "package", "sce_sys", "icon0.png"), os.path.join(pkg_dir, "sce_sys", "icon0.png"))
    shutil.copy2(LIBC_PRX, os.path.join(pkg_dir, "sce_module", "libc.prx"))
    shutil.copy2(baserom, os.path.join(pkg_dir, "data", "sm64_ps5", "baserom.us.z64"))

    # Process param.json
    with open(os.path.join(HERE, "package", "sce_sys", "param.json"), "r") as f:
        param_content = f.read()
    param_content = param_content.replace("@TITLE_ID@", TITLE_ID).replace("@TITLE_NAME@", TITLE_NAME)
    with open(os.path.join(pkg_dir, "sce_sys", "param.json"), "w") as f:
        f.write(param_content)

    print(f"DevKit title folder ready: {pkg_dir}")

if __name__ == "__main__":
    main()
