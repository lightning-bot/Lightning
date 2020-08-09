
import re
import setuptools

with open("lightning/meta.py") as f:
    version = re.search(
        r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]', f.read(), re.MULTILINE
    ).group(1)


setuptools.setup(
    name="Lightning.py",
    description="Multi-purpose Discord bot.",
    license="GNU Affero General Public License - Version 3",
    author="LightSage",
    version=version,
    packages=[
        "lightning",
        "lightning.cogs",
        "lightning.utils",
    ],
    include_package_data=True,
    dependency_links=[
        # jishaku
        "git+https://gitlab.com/Gorialis/jishaku@master#egg=jishaku",
        # d.py ext.menus
        "git+https://github.com/Rapptz/discord-ext-menus@refs/pull/5/merge",
        # https://github.com/bear/parsedatetime/pull/239
        "git+https://github.com/bear/parsedatetime@7a759c1f8ff7563f12ac2c1f2ea0b41452f61dec#egg=parsedatetime"],
    install_requires=[
        "uvloop",
        "python-dateutil",
        "Pillow",
        "asyncpg",
        "feedparser",
        "toml",
        "lru_dict",
        "dpy-ui",
        "fuzzywuzzy[speedup]",
        "discord-flags",
        "tabulate",
        "uwuify",
        "psutil",
        "aredis",
        "hiredis",
        "discord.py @ git+https://github.com/Rapptz/discord.py@refs/pull/1849/merge#egg=discord.py"]
)
