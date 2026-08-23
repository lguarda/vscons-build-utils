"""
This is an scons builder to replace cake from vintage story mod template because why not
it probably only work on linux
"""

import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from SCons.Script import Alias, AlwaysBuild
from SCons.Variables import BoolVariable, EnumVariable, PathVariable

HOME = os.environ.get("HOME")
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
TEMPLATE_DIR = os.path.join(SCRIPT_DIR, "..", "template")

# Build variables
def get_scons_vs_option(vars):
    """Register the Vintage Story related SCons command-line variables."""
    vars.Add(
        PathVariable(
            "VINTAGE_STORY",
            "Vintage Story install path",
            "/opt/Vintagestory/",
            PathVariable.PathAccept,
        )
    )
    vars.Add(
        PathVariable(
            "VINTAGE_STORY_DATA",
            "Vintage Story data path where the Mods folder lives",
            f"{HOME}/.config/VintagestoryData/",
            PathVariable.PathAccept,
        )
    )
    vars.Add(
        EnumVariable(
            "DOTNET_VERS",
            help="dotnet target version, depends on the VS release",
            default="net10.0",
            allowed_values=("net8.0", "net10.0"),
        )
    )
    vars.Add(
        BoolVariable(
            "DEBUG",
            "Build mods in Debug configuration (enables #if DEBUG code)",
            False,
        )
    )


# Inject shared env for dotnet cmd
def _vs_env(env, extra=None):
    """Build a subprocess environment carrying the VS/dotnet SCons vars."""
    proc_env = os.environ.copy()
    proc_env["VINTAGE_STORY"] = str(env["VINTAGE_STORY"])
    proc_env["DOTNET_VERS"] = str(env["DOTNET_VERS"])
    if extra:
        proc_env.update(extra)
    return proc_env


def _run_cmd(cmd, env=None, **kwargs):
    # print("Running:", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, env=env, **kwargs)


def vs_version(env):
    cmd = [f"{env['VINTAGE_STORY']}/Vintagestory", "--version"]
    output = _run_cmd(cmd, capture_output=True, text=True).stdout.rstrip()
    # print(f"Output: {output}")
    return output


def vs_run_game(env):
    cmd = [
        f"{env['VINTAGE_STORY']}/Vintagestory",
        "-o", f"moddebug-{vs_version(env)}",
        "--dataPath", str(env["VINTAGE_STORY_DATA"]),
    ]
    _run_cmd(cmd)


def dotnet_fmt(csproj, env):
    _run_cmd(["dotnet", "format", csproj], env=_vs_env(env))

# don't work with dotnet 10 yet
def roslynator(csproj, env):
    cmd = [f"{HOME}/.dotnet/tools/roslynator", "analyze", csproj]
    _run_cmd(cmd, env=_vs_env(env))

# Build section

def _configuration(env):
    return "Debug" if env["DEBUG"] else "Release"

def validate_json_assets(mod_dir):
    """Raise if any *.json under <mod_dir>/assets is malformed."""
    assets_dir = Path(mod_dir) / "assets"
    if not assets_dir.is_dir():
        return
    for f in assets_dir.rglob("*.json"):
        try:
            json.loads(f.read_text())
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Validation failed for JSON file: {f}\n{e}") from e

# This is taken from Program.cs cake build system
def build_mod_release(mod_dir, mod_id, version, env, release_dir="Release"):
    """Clean, publish, validate assets and zip a mod into release_dir/<id>_<version>.zip."""
    csproj = f"{mod_dir}/{mod_dir}.csproj"
    configuration = _configuration(env)

    _run_cmd(["dotnet", "clean", csproj, "-c", configuration], env=_vs_env(env))
    validate_json_assets(mod_dir)
    _run_cmd(["dotnet", "publish", csproj, "-c", configuration], env=_vs_env(env))

    publish_dir = Path(mod_dir) / "bin" / configuration / "Mods" / "mod" / "publish"
    stage = Path(release_dir) / mod_id
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    for item in publish_dir.glob("*"):
        dest = stage / item.name
        shutil.copytree(item, dest, dirs_exist_ok=True) if item.is_dir() else shutil.copy2(item, dest)

    assets_dir = Path(mod_dir) / "assets"
    if assets_dir.is_dir():
        shutil.copytree(assets_dir, stage / "assets", dirs_exist_ok=True)

    shutil.copy2(Path(mod_dir) / "modinfo.json", stage / "modinfo.json")

    modicon = Path(mod_dir) / "modicon.png"
    if modicon.is_file():
        shutil.copy2(modicon, stage / "modicon.png")

    zip_path = Path(release_dir) / f"{mod_id}_{version}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in stage.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(stage))
    return zip_path


def git_version():
    try:
        return (
            subprocess.check_output(
                ["git", "describe", "--tags", "--always"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def setup_modinfo(env, target_dir, server, client, mod_id, mod_name, desc):
    return env.Substfile(
        target=f"{target_dir}/modinfo.json",
        source=f"{TEMPLATE_DIR}/modinfo.json.in",
        SUBST_DICT={
            "@AUTHOR@": "lguarda",
            "@GIT_VERSION@": env["GIT_VERSION"],
            "@WITH_SERVER@": "true" if server else "false",
            "@WITH_CLIENT@": "true" if client else "false",
            "@MOD_ID@": mod_id,
            "@MOD_NAME@": mod_name,
            "@DESCRIPTION@": desc,
        },
    )

# This can be used to backup and restore save for testing
# make_copy_target("backupsave", f"{env['VINTAGE_STORY_DATA']}/Saves", f"{env['VINTAGE_STORY_DATA']}/Saves.bak")
# make_copy_target("restoresave", f"{env['VINTAGE_STORY_DATA']}/Saves.bak", f"{env['VINTAGE_STORY_DATA']}/Saves")
def make_copy_target(name, src, dst):
    src = os.path.expanduser(src)
    dst = os.path.expanduser(dst)

    def action(target, source, env):
        if not os.path.exists(src):
            raise RuntimeError(f"Source does not exist: {src}")
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"[{name}]\n  {src}\n    -> {dst}")

    target = Alias(name, [], action)
    AlwaysBuild(target)
    return target
