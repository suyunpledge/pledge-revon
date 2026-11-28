"""Bridge workspace-granted, host-owned compute packs into the desktop tool list."""
from pathlib import Path

from pack_runtime import PACKS, install
from plugin_market import MANIFEST_FIELDS, MANIFEST_NAME, Marketplace, market_lock
from plugin_capabilities import CapabilityRuntime


def activate(market, pid, workspace):
    if pid not in PACKS:
        raise ValueError("未知能力包。")
    with market_lock(market.market_dir / "state.lock"):
        official = next(p for p in market.builtin_entries() if p.id == pid)
        current = market.find(pid)
        fields = [name for name in MANIFEST_FIELDS if name != "source"]

        def matches(plugin):
            return plugin and all(getattr(plugin, k) == getattr(official, k) for k in fields)

        if not matches(current):
            raise ValueError("能力包清单与内置版本不符。")
        p = market.install_from_catalog(pid)
        if not matches(p) or {f.name for f in Path(p.path).iterdir()} != {MANIFEST_NAME}:
            raise ValueError("能力包安装目录与内置清单不符。")
        if p.needs_ack:
            p = market.ack(pid, expected_fingerprint=p.ack_of())
        fingerprint, generation = p.ack_of(), p.generation
    # Downloads can take time; leave the marketplace available to other windows.
    install(market.home, pid)
    with market_lock(market.market_dir / "state.lock"):
        p = market.find(pid)
        if not p or not p.installed or p.needs_ack or (p.ack_of(), p.generation) != (fingerprint, generation):
            raise ValueError("安装期间插件状态已更改，请重新确认。")
        if not p.enabled:
            p = market.enable(pid)
        if "compute.local" not in p.granted_capabilities(workspace):
            market.grant(pid, ["compute.local"], workspace, expected_fingerprint=p.ack_of())
        return {"enabled": pid, "workspace": str(workspace)}


def with_packs(connection, home, workspace):
    tools, dispatch = connection
    market = Marketplace(home)
    if not any((market.plugins_dir / pid).is_dir() for pid in PACKS):
        return connection
    catalog = [p for p in market.catalog() if p.id in PACKS]
    runtime = CapabilityRuntime(market, workspace, "", None)
    runtime.reload(plugins=catalog, reserved_names=set(tools), available_targets=[])
    tools = dict(tools)
    for schema in runtime.openai_schemas(catalog):
        name = schema["function"]["name"]
        tools[name] = schema, ("compute_pack", name)

    def route(target, args, cancel):
        if isinstance(target, tuple) and target[0] == "compute_pack":
            if cancel is not None and cancel.is_set():
                return {"ok": False, "error": "已取消能力包调用。"}
            return runtime.call(target[1], args)
        return dispatch(target, args, cancel)

    return tools, route
