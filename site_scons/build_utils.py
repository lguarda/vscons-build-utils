import subprocess
import os
from SCons.Variables import Variables
from SCons.Variables import BoolVariable, EnumVariable, PathVariable
from SCons.Script import Alias, AlwaysBuild
import shutil


home = os.environ.get("HOME")
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

def git_version():
    try:
        return subprocess.check_output(
            ["git", "describe", "--tags", "--always"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"

def vs_version(env):
    cmd = [
        f"{env['VINTAGE_STORY']}/Vintagestory",
        "--version"
    ]
    print("Running:", {" ".join(cmd)})
    output = subprocess.check_output(cmd, text=True).rstrip()
    print(f"Output:{output}")
    return output

def vs_run(env):
    cmd = [
        f"{env['VINTAGE_STORY']}/Vintagestory",
        "-o", f"moddebug-{vs_version(env)}",
        "--dataPath", str(env["VINTAGE_STORY_DATA"]),
    ]

    print("Running vs with:", " ".join(cmd))
    subprocess.run(cmd)


def cake_package(csproj, vs_path, dotnet_vers):
    proc_env = os.environ.copy()
    proc_env["VINTAGE_STORY"] = vs_path
    proc_env["DOTNET_VERS"] = dotnet_vers
    cmd = [
        "dotnet",
        "run",
        "--project",
        csproj,
    ]
    subprocess.run(cmd, env=proc_env)

def roslynator(target, source, env):
    proc_env = os.environ.copy()
    proc_env["VINTAGE_STORY"] = str(env["VINTAGE_STORY"])
    cmd = [
        f"{home}/.dotnet/tools/roslynator",
        "analyze",
        "SmartCursorPlus/SmartCursor.csproj",
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, env=proc_env)

def get_scons_vs_option(vars):
    vars.Add(
        PathVariable(
            'VINTAGE_STORY',
            'Vintage story path',
            '/opt/Vintagestory/',   # default
            PathVariable.PathAccept
        )
    )
    vars.Add(
        PathVariable(
            'VINTAGE_STORY_DATA',
            'Vintage story data path where mod folder is located',
            f'{home}/.config/VintagestoryData/',   # default
            PathVariable.PathAccept
        )
    )
    vars.Add(
        EnumVariable(
            "DOTNET_VERS",
            help="Used dotnet version which depends on vs release",
            default="net8.0",
            allowed_values=("net8.0", "net10.0"),
            map={},
            ignorecase=0,  # case-sensitive
        ),
    )


def setup_cake_build(env, target_dir, project_name, release_dir):
    cake_target_csproj = env.Substfile(
        target=f"{target_dir}/Program.cs",
        source=f"{SCRIPT_DIR}/../template/CakeBuild/Program.cs",
        SUBST_DICT={
            "PROJECT_NAME": project_name,
            "RELEASE_DIR" : release_dir
            }
    )
    cake_target_program = env.Install(target_dir, f"{SCRIPT_DIR}/../template/CakeBuild/CakeBuild.csproj")
    return [cake_target_csproj, cake_target_program]


def setup_modinfo(env, target_dir, server, client, mod_id, mod_name, desc):
    return env.Substfile(
        target=f"{target_dir}/modinfo.json",
        source=f"{SCRIPT_DIR}/../template/modinfo.json.in",
        SUBST_DICT={
            "@AUTHOR@": "lguarda",
            "@GIT_VERSION@": env["GIT_VERSION"],
            "@WITH_SERVER@": 'true' if server else 'false',
            "@WITH_CLIENT@": 'true' if client else 'false',
            "@MOD_ID@": mod_id,
            "@MOD_NAME@": mod_name,
            "@DESCRIPTION@": desc,
            }
)

def make_copy_target(name, src, dst):
    src = os.path.expanduser(src)
    dst = os.path.expanduser(dst)

    def action(target, source, env):
        if not os.path.exists(src):
            raise RuntimeError(f"Source does not exist: {src}")

        if os.path.exists(dst):
            shutil.rmtree(dst)

        shutil.copytree(src, dst)

        print(f"[{name}]")
        print(f"  {src}")
        print(f"    -> {dst}")

    target = Alias(name, [], action)
    AlwaysBuild(target)

    return target
