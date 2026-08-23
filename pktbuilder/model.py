"""Topology file model: parse, validate, normalize.

A topology file (YAML, or JSON if you prefer) looks like:

    name: tiny-lab
    notes:
      - {x: 100, y: 40, text: "core"}
    devices:
      - name: R1
        kind: router
        x: 200
        y: 120
        config: |
          enable
          configure terminal
          hostname R1
          ...
      - name: SW1
        kind: switch
        x: 200
        y: 260
        config_file: configs/sw1.txt
      - name: PC1
        kind: pc
        x: 80
        y: 300
        ip: 192.168.10.11
        mask: 255.255.255.0
        gateway: 192.168.10.1
        dns: 192.168.10.10
      - name: SRV1
        kind: server
        ip: 192.168.10.10
        mask: 255.255.255.0
        gateway: 192.168.10.1
        dns_records:
          - [web.local, 192.168.10.10]
    links:
      - [R1, GigabitEthernet0/0, SW1, GigabitEthernet0/1]
      - [SW1, FastEthernet0/3, PC1, FastEthernet0]

Validation is deliberately strict: anything wrong fails at load time with a
ToplogyError naming the device/link, never deep inside XML generation.
"""

import os
import re

try:
    import yaml
except ModuleNotFoundError:                       # pragma: no cover
    yaml = None


class TopologyError(ValueError):
    """Raised for any problem in the user's topology file."""


KINDS = ("router", "switch", "pc", "server")

SWITCH_FAST = 24
SWITCH_GIG = 2

_DOTTED = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_PORTNAME = re.compile(r"^(FastEthernet|GigabitEthernet|Serial)"
                       r"\d+(/\d+)*$")


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _require_mapping(obj, what):
    if not isinstance(obj, dict):
        raise TopologyError("%s must be a mapping, got %s"
                            % (what, type(obj).__name__))


def _check_ip(value, what, field):
    if value in (None, ""):
        return
    if not _DOTTED.match(str(value)):
        raise TopologyError("%s: %s %r is not a dotted-quad IPv4 address"
                            % (what, field, value))
    for octet in str(value).split("."):
        if int(octet) > 255:
            raise TopologyError("%s: %s %r has an octet > 255"
                                % (what, field, value))
    if not _is_mask(str(value)) and field == "mask":
        raise TopologyError("%s: mask %r is not a contiguous netmask"
                            % (what, value))


def _is_mask(value):
    bits = "".join(bin(int(o))[2:].zfill(8)
                   for o in value.split("."))
    return re.match(r"^1+0*$", bits) is not None


def _check_xy(dev, value, field):
    try:
        float(value)
    except (TypeError, ValueError):
        raise TopologyError("device %s: %s must be a number, got %r"
                            % (dev, field, value))


def switch_ports():
    names = set()
    for i in range(1, SWITCH_FAST + 1):
        names.add("FastEthernet0/%d" % i)
    for i in range(0, SWITCH_GIG + 1):
        names.add("GigabitEthernet0/%d" % i)
    return names


HOST_PORTS = {"FastEthernet0"}


def router_physical_ports(config_text):
    """Physical interfaces declared in an IOS config (subinterfaces kept:
    their physical parent is derived by the builder)."""
    ports = set()
    for m in re.finditer(r"^interface (\S+)\s*$", config_text or "",
                         flags=re.M):
        name = m.group(1)
        if not _PORTNAME.match(name):
            continue
        ports.add(name.split(".")[0])
        ports.add(name)
    return ports


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def load_topology(path):
    """Parse a topology YAML/JSON file into a normalized dict.

    Raises TopologyError with a precise message on any problem.
    """
    if not os.path.exists(path):
        raise TopologyError("topology file not found: %s" % path)
    raw = open(path, "r", encoding="utf-8").read()
    base = os.path.dirname(os.path.abspath(path))

    if path.endswith((".yaml", ".yml")):
        if yaml is None:
            raise TopologyError("PyYAML is required for .yaml files "
                                "(pip install pyyaml)")
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise TopologyError("invalid YAML: %s" % exc)
    else:
        import json
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TopologyError("invalid JSON: %s" % exc)

    spec = validate_spec(data, base=base)
    spec["source_path"] = path
    return spec


# ---------------------------------------------------------------------------
# validation / normalization
# ---------------------------------------------------------------------------

def validate_spec(data, base="."):
    _require_mapping(data, "topology document")

    name = data.get("name") or "packettracer-topology"
    if not re.match(r"^[\w\- ]+$", str(name)):
        raise TopologyError("name %r may only contain letters, digits, "
                            "'-', '_' and spaces" % name)

    devices_in = data.get("devices")
    if not isinstance(devices_in, list) or not devices_in:
        raise TopologyError("'devices' must be a non-empty list")

    devices = []
    seen_names = set()
    used_ports = {}                      # dev -> {port}
    index = {}

    for raw in devices_in:
        dev = _validate_device(raw, base)
        if dev["name"] in seen_names:
            raise TopologyError("duplicate device name: %s" % dev["name"])
        seen_names.add(dev["name"])
        index[dev["name"]] = len(devices)
        used_ports[dev["name"]] = set()
        devices.append(dev)

    links = []
    links_in = data.get("links", [])
    if not isinstance(links_in, list):
        raise TopologyError("'links' must be a list")
    if not links_in:
        raise TopologyError("topology has no 'links': every device would be "
                            "isolated")
    for raw in links_in:
        link = _validate_link(raw, index, devices)
        key_a = link["a_dev"]
        key_b = link["b_dev"]
        if link["a_port"] in used_ports[key_a]:
            raise TopologyError("device %s: port %s used by more than one "
                                "link" % (key_a, link["a_port"]))
        if link["b_port"] in used_ports[key_b]:
            raise TopologyError("device %s: port %s used by more than one "
                                "link" % (key_b, link["b_port"]))
        used_ports[key_a].add(link["a_port"])
        used_ports[key_b].add(link["b_port"])
        links.append(link)

    notes = []
    for raw in (data.get("notes") or []):
        if isinstance(raw, str):
            notes.append({"x": 20, "y": 20, "text": raw})
            continue
        _require_mapping(raw, "note entry")
        if "text" not in raw:
            raise TopologyError("note entry missing 'text'")
        notes.append({"x": int(raw.get("x", 20)),
                      "y": int(raw.get("y", 20)),
                      "text": str(raw["text"])})

    return {
        "name": str(name),
        "devices": devices,
        "links": links,
        "notes": notes,
        "device_index": index,
    }


def _load_config_field(dev_name, raw, base):
    inline = raw.get("config")
    ref = raw.get("config_file")
    if inline and ref:
        raise TopologyError("device %s: give either 'config' or "
                            "'config_file', not both" % dev_name)
    if ref:
        path = os.path.join(base, ref)
        if not os.path.exists(path):
            raise TopologyError("device %s: config_file not found: %s"
                                % (dev_name, path))
        return open(path, encoding="utf-8").read()
    if inline is None:
        return ""
    if not isinstance(inline, str):
        raise TopologyError("device %s: 'config' must be a string block"
                            % dev_name)
    return inline


def _validate_device(raw, base):
    _require_mapping(raw, "device entry")
    dname = raw.get("name")
    if not dname or not re.match(r"^[\w\-.]+$", str(dname)):
        raise TopologyError("every device needs a simple 'name' "
                            "(letters/digits/-/_/.), got %r" % dname)

    kind = raw.get("kind")
    if kind not in KINDS:
        raise TopologyError(
            "device %s: kind must be one of %s, got %r"
            % (dname, "/".join(KINDS), kind))

    dev = {
        "name": str(dname),
        "kind": kind,
        "config": _load_config_field(str(dname), raw, base),
        "x": raw.get("x", 100),
        "y": raw.get("y", 100),
    }
    _check_xy(dname, dev["x"], "x")
    _check_xy(dname, dev["y"], "y")

    if kind == "router":
        if not dev["config"].strip():
            raise TopologyError("router %s: routers need IOS 'config' or "
                                "'config_file'" % dname)
        ports = router_physical_ports(dev["config"])
        if not ports:
            raise TopologyError("router %s: its config declares no usable "
                                "interfaces" % dname)
        dev["ports"] = sorted(ports)

    elif kind == "switch":
        if not dev["config"].strip():
            # a factory switch is fine; PT will boot it unconfigured
            dev["config"] = ("enable\nconfigure terminal\nhostname %s\n"
                             "end\n" % dname)
        dev["ports"] = sorted(switch_ports())

    else:
        fields = {}
        for src, dst in (("ip", "ip"), ("mask", "mask"),
                         ("gateway", "gw"), ("dns", "dns")):
            fields[dst] = str(raw.get(src, "") or "")
        dhcp = bool(raw.get("dhcp", False))
        filled = [k for k in ("ip", "mask", "gw") if fields[k]]
        if filled and len(filled) != 3:
            missing = {"ip", "mask", "gw"} - set(filled)
            raise TopologyError(
                "device %s: static addressing needs ip+mask+gateway; "
                "missing %s" % (dname, ", ".join(sorted(missing))))
        if not dhcp and not filled and kind == "pc":
            # pure DHCP client without lease: allowed but flagged at build
            pass
        for k in ("ip", "mask", "gw", "dns"):
            if k == "mask" and fields[k] and not _is_mask(fields[k]):
                raise TopologyError("device %s: mask %r is not contiguous"
                                    % (dname, fields[k]))
            if k != "mask":
                _check_ip(fields[k], "device %s" % dname,
                          {"ip": "ip", "gw": "gateway", "dns": "dns"}[k])
        dev.update(fields)
        dev["dhcp"] = dhcp

        records = raw.get("dns_records") or []
        if kind == "server" and records:
            norm = []
            for rec in records:
                if isinstance(rec, (list, tuple)) and len(rec) == 2:
                    norm.append((str(rec[0]), str(rec[1])))
                elif isinstance(rec, dict) and "name" in rec and \
                        "ip" in rec:
                    norm.append((str(rec["name"]), str(rec["ip"])))
                else:
                    raise TopologyError(
                        "device %s: dns_records entries must be "
                        "[name, ip] pairs" % dname)
                nm, ipaddr = norm[-1]
                _check_ip(ipaddr, "device %s dns_records[%s]" % (dname, nm),
                          "ip")
            dev["records"] = norm

    return dev


def _parse_endpoint(raw, side, index):
    """Accept [dev, port] lists or {device:, port:} dicts."""
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        dev, port = raw
    elif isinstance(raw, dict):
        dev, port = raw.get("device"), raw.get("port")
    else:
        raise TopologyError("link %s endpoint must be [device, port], got %r"
                            % (side, raw))
    dev = str(dev)
    port = str(port)
    if dev not in index:
        raise TopologyError("link references unknown device %r" % dev)
    return dev, port


def _validate_link(raw, index, devices):
    if isinstance(raw, dict) and ("a" in raw or "b" in raw):
        a_raw, b_raw = raw.get("a"), raw.get("b")
    elif isinstance(raw, list) and len(raw) == 4:
        a_raw, b_raw = raw[:2], raw[2:]
    else:
        raise TopologyError(
            "each link must be [devA, portA, devB, portB] or "
            "{a: [...], b: [...]}, got %r" % (raw,))

    ade, aport = _parse_endpoint(a_raw, "a", index)
    bde, bport = _parse_endpoint(b_raw, "b", index)
    if ade == bde:
        raise TopologyError("link connects device %s to itself" % ade)

    da = devices[index[ade]]
    db = devices[index[bde]]
    _check_endpoint_port(da, aport)
    _check_endpoint_port(db, bport)

    serial = ("Serial" in aport) or ("Serial" in bport)
    if serial and not (aport.startswith("Serial") and
                       bport.startswith("Serial")):
        raise TopologyError("serial cable needs Serial ports on BOTH ends "
                            "(%s:%s <-> %s:%s)" % (ade, aport, bde, bport))
    if serial and (da["kind"] != "router" or db["kind"] != "router"):
        raise TopologyError("serial cables connect two ROUTERS only "
                            "(%s is %s, %s is %s)"
                            % (ade, da["kind"], bde, db["kind"]))
    if not serial and (da["kind"] == "router" and db["kind"] == "router"):
        raise TopologyError(
            "two routers cannot be cabled over copper (%s <-> %s); use a "
            "Serial link" % (ade, bde))

    return {
        "type": "eSerial" if serial else "eCopper",
        "a_dev": ade, "a_port": aport,
        "b_dev": bde, "b_port": bport,
    }


def _check_endpoint_port(dev, port):
    dname, kind = dev["name"], dev["kind"]
    if not _PORTNAME.match(port):
        raise TopologyError("device %s: port name %r is malformed"
                            % (dname, port))
    if kind == "pc" or kind == "server":
        if port not in HOST_PORTS:
            raise TopologyError("device %s (%s) only has %s, got %r"
                                % (dname, kind, ", ".join(sorted(HOST_PORTS)),
                                   port))
        return
    if kind == "switch":
        if port not in switch_ports():
            raise TopologyError(
                "switch %s (2960-24TT) has no port %r; valid: "
                "FastEthernet0/1-24, GigabitEthernet0/0-2" % (dname, port))
        return
    # router: port must exist in its parsed config
    if port.split(".")[0] not in dev["ports"]:
        raise TopologyError(
            "router %s: interface %r does not exist in its config; "
            "declared: %s" % (dname, port, ", ".join(dev["ports"])))
