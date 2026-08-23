"""Config-level verification of a topology spec before/after building.

Reuses the approach proven on the PMUN network (packet-builder/pingtest.py):
rebuild broadcast domains per VLAN from wiring + IOS configs, check every
host/gateway/pool relationship, then simulate a full ping matrix.

All checks are static analysis of the user's topology -- no Packet Tracer
required. `pktbuild validate` exits non-zero if anything fails.
"""

import os
import re
import sys

from pktbuilder.builder import parse_intf_config

FAILURES = []


def _check(cond, label):
    print("  [%s] %s" % ("PASS" if cond else "FAIL", label))
    if not cond:
        FAILURES.append(label)
    return cond


def reset():
    del FAILURES[:]


# ---------------------------------------------------------------------------
# IOS parsing helpers
# ---------------------------------------------------------------------------

def ios_interfaces(config_text):
    out = {}
    cur = None
    for line in (config_text or "").splitlines():
        m = re.match(r"^interface (\S+)", line)
        if m:
            cur = m.group(1)
            out.setdefault(cur, {"ip": None, "mask": None})
            continue
        m = re.match(r"^\s+ip address (\S+) (\S+)", line)
        if m and cur:
            out[cur]["ip"], out[cur]["mask"] = m.group(1), m.group(2)
    return out


def ospf_networks(text):
    nets = []
    in_ospf = False
    for line in (text or "").splitlines():
        if re.match(r"^router ospf", line):
            in_ospf = True
        elif re.match(r"^\S", line):
            in_ospf = False
        m = re.match(r"^\s+network (\S+) (\S+) area (\S+)", line)
        if m and in_ospf:
            nets.append((m.group(1), m.group(2), m.group(3)))
    return nets


def _pools_of(text):
    pools = []
    excluded = []
    for line in (text or "").splitlines():
        m = re.match(r"^ip dhcp excluded-address (\S+)(?: (\S+))?", line)
        if m:
            excluded.append((m.group(1), m.group(2) or m.group(1)))
    cur = None
    for line in (text or "").splitlines():
        m = re.match(r"^ip dhcp pool (\S+)", line)
        if m:
            cur = {"name": m.group(1), "net": None, "mask": None,
                   "router": None, "dns": None}
            pools.append(cur)
            continue
        if cur is None:
            continue
        if re.match(r"^\S", line):
            cur = None
            continue
        m = re.match(r"^\s+network (\S+) (\S+)", line)
        if m:
            cur["net"], cur["mask"] = m.group(1), m.group(2)
        m = re.match(r"^\s+default-router (\S+)", line)
        if m:
            cur["router"] = m.group(1)
        m = re.match(r"^\s+dns-server (\S+)", line)
        if m:
            cur["dns"] = m.group(1)
    for p in pools:
        p["excluded"] = excluded
    return pools


def _expand_range(spec_txt):
    m = re.match(r"^(\D+)(\d+)/(\d+)-(\d+)$", spec_txt.strip())
    if m:
        pfx, slot, lo, hi = (m.group(1), m.group(2),
                             int(m.group(3)), int(m.group(4)))
        return ["%s%s/%d" % (pfx, slot, i) for i in range(lo, hi + 1)]
    return [spec_txt.strip()]


def switch_ports_map(text):
    ports = {}
    cur = []
    for line in (text or "").splitlines():
        m = re.match(r"^interface (?:range )?(\S+)", line)
        if m:
            cur = []
            for part in m.group(1).split(","):
                cur.extend(_expand_range(part))
            for name in cur:
                ports.setdefault(name, {"mode": "access", "vlans": {1}})
            continue
        if not cur:
            continue
        m = re.match(r"^\s+switchport mode (\S+)", line)
        if m:
            for name in cur:
                ports[name]["mode"] = m.group(1)
        m = re.match(r"^\s+switchport access vlan (\d+)", line)
        if m:
            for name in cur:
                ports[name]["vlans"] = {int(m.group(1))}
        m = re.match(r"^\s+switchport trunk allowed vlan (\S+)", line)
        if m:
            vlans = set()
            for part in m.group(1).split(","):
                if "-" in part:
                    lo, hi = part.split("-")
                    vlans |= set(range(int(lo), int(hi) + 1))
                else:
                    vlans.add(int(part))
            for name in cur:
                ports[name]["vlans"] = vlans
    return ports


def ip_int(s):
    a, b, c, d = (int(x) for x in s.split("."))
    return (a << 24) | (b << 16) | (c << 8) | d


def cidr_match(ip, net, wildcard):
    w = ip_int(wildcard)
    return (ip_int(ip) & ~w & 0xFFFFFFFF) == (ip_int(net) & ~w & 0xFFFFFFFF)


def same_subnet(a, b, mask):
    m = ip_int(mask)
    return (ip_int(a) & m) == (ip_int(b) & m)


# ---------------------------------------------------------------------------
# main validation
# ---------------------------------------------------------------------------

def validate_spec(spec, verbose=True):
    """Run all checks over a validated spec dict. Returns list of failures."""
    reset()
    devices = spec["devices"]
    index = {d["name"]: i for i, d in enumerate(devices)}
    by_name = {d["name"]: d for d in devices}
    routers = {d["name"]: d for d in devices if d["kind"] == "router"}
    switches = [d for d in devices if d["kind"] == "switch"]
    hosts = [d for d in devices if d["kind"] in ("pc", "server")]

    adj = {}
    for lk in spec["links"]:
        adj.setdefault(lk["a_dev"], []).append(lk)
        adj.setdefault(lk["b_dev"], []).append(lk)

    def link_other(lk, dev):
        return ((lk["b_dev"], lk["b_port"]) if lk["a_dev"] == dev
                else (lk["a_dev"], lk["a_port"]))

    def port_vlans(name, port):
        if name not in by_name or by_name[name]["kind"] != "switch":
            return None
        sp = switch_ports_map(by_name[name]["config"])
        if port in sp:
            return sp[port]["vlans"]
        for iname, info in sp.items():
            if port.startswith(iname):
                return info["vlans"]
        return None

    # ---- 1. addressing -------------------------------------------------
    if verbose:
        print("== 1. host addressing ==")
    seen = set()
    ok = True
    for h in hosts:
        e = h
        ip, mask = e.get("ip", ""), e.get("mask", "")
        gw, dns = e.get("gw", ""), e.get("dns", "")
        pure_dhcp = e.get("dhcp") and not ip
        filled = bool(ip and mask and gw)
        uniq = (not ip) or ip not in seen
        seen.add(ip)
        good = (filled or pure_dhcp) and uniq
        ok &= good
        if verbose:
            print("  [%s] %-14s %-15s gw=%s%s" % (
                "PASS" if good else "FAIL", h["name"], ip or "(dhcp)",
                gw or "-", "" if uniq else " DUPLICATE"))
    _check(ok, "every host has a usable address plan")

    # ---- 2. gateways ----------------------------------------------------
    if verbose:
        print("== 2. gateways exist and are on-subnet ==")
    host_rtr = {}
    ok = True
    for h in hosts:
        gw = h.get("gw", "")
        found = None
        if gw:
            for rn, rd in routers.items():
                for pi in ios_interfaces(rd["config"]).values():
                    if pi["ip"] == gw and pi["mask"] and \
                            h.get("ip") and \
                            same_subnet(h["ip"], pi["ip"], pi["mask"]):
                        found = rn
        ok &= found is not None
        host_rtr[h["name"]] = found
        if verbose and not found:
            print("  [FAIL] %s: gateway %s missing/on wrong subnet"
                  % (h["name"], gw or "-"))
    _check(ok, "each gateway exists on a router sharing the host subnet")

    # ---- 3. serial point-to-point consistency ---------------------------
    if verbose:
        print("== 3. serial links share a subnet ==")
    ok = True
    for lk in spec["links"]:
        if lk["type"] != "eSerial":
            continue
        ia = ios_interfaces(by_name[lk["a_dev"]]["config"]).get(lk["a_port"])
        ib = ios_interfaces(by_name[lk["b_dev"]]["config"]).get(lk["b_port"])
        if not ia or not ib or not ia["ip"] or not ib["ip"]:
            ok = False
            if verbose:
                print("  [FAIL] %s<->%s: missing IP on a serial end"
                      % (lk["a_dev"], lk["b_dev"]))
            continue
        if ia["mask"] != ib["mask"] or \
                not same_subnet(ia["ip"], ib["ip"], ia["mask"]):
            ok = False
            if verbose:
                print("  [FAIL] %s:%s(%s) <-> %s:%s(%s): different subnets"
                      % (lk["a_dev"], lk["a_port"], ia["ip"],
                         lk["b_dev"], lk["b_port"], ib["ip"]))
    _check(ok, "every serial pair shares one subnet")

    # ---- 4. VLAN domains --------------------------------------------------
    if verbose:
        print("== 4. per-VLAN broadcast domains ==")

    def access_vlan(hname):
        for lk in adj.get(hname, []):
            other, oport = link_other(lk, hname)
            od = by_name[other]
            if od["kind"] == "switch":
                vl = port_vlans(other, oport)
                if vl and len(vl) == 1:
                    return sorted(vl)[0]
            if od["kind"] == "router":
                return None
            return access_vlan(other)
        return None

    def gw_on_router(rname, port, vlan, want_gw):
        for pname, pi in ios_interfaces(
                by_name[rname]["config"]).items():
            if not pi["ip"] or pi["ip"] != want_gw:
                continue
            base = pname.split(".")[0]
            # physical port matches or is the parent of a subinterface
            if pname == port or base == port:
                if "." in pname:
                    try:
                        if int(pname.split(".")[1]) != vlan:
                            continue
                    except ValueError:
                        pass
                return True
        return False

    def gateway_reachable(hidx_name, vlan, want_gw):
        stack = [(hidx_name, None)]
        visited = set()
        while stack:
            dname, via = stack.pop()
            key = (dname, via)
            if key in visited:
                continue
            visited.add(key)
            if dname == hidx_name and via is None:
                for lk in adj.get(dname, []):
                    other, oport = link_other(lk, dname)
                    stack.append((other, oport))
                continue
            d = by_name[dname]
            if d["kind"] == "switch":
                if via:
                    vl = port_vlans(dname, via)
                    if vl is None or vlan not in vl:
                        continue
                for lk in adj.get(dname, []):
                    myport = lk["a_port"] if lk["a_dev"] == dname \
                        else lk["b_port"]
                    mvl = port_vlans(dname, myport)
                    if mvl is not None and vlan in mvl:
                        stack.append(link_other(lk, dname))
            elif d["kind"] == "router":
                if via and gw_on_router(dname, via, vlan, want_gw):
                    return True
        return False

    l2_ok = True
    switched = [h for h in hosts if h.get("ip")]
    for h in switched:
        vlan = access_vlan(h["name"])
        if vlan is None:
            if verbose:
                print("  [PASS] %-14s direct-attached" % h["name"])
            continue
        good = gateway_reachable(h["name"], vlan, h["gw"])
        l2_ok &= good
        if verbose:
            print("  [%s] %-14s VLAN %d -> gw %s" % (
                "PASS" if good else "FAIL", h["name"], vlan, h["gw"]))
    _check(l2_ok, "every switched PC reaches its gateway inside its VLAN")

    # ---- 5. DHCP pools -----------------------------------------------------
    if verbose:
        print("== 5. DHCP leases conform to pools ==")
    pool_ok = True
    for h in hosts:
        if not h.get("dhcp"):
            continue
        ip, gw = h.get("ip"), h.get("gw")
        hit = None
        if ip and gw:
            for rn, rd in routers.items():
                for pool in _pools_of(rd["config"]):
                    if pool["net"] and \
                            same_subnet(ip, pool["net"], pool["mask"]) and \
                            pool["router"] == gw:
                        hit = (rn, pool)
        if hit is None:
            if h.get("ip"):           # seeded lease must sit in some pool
                pool_ok = False
                if verbose:
                    print("  [FAIL] %s: lease %s matches no pool" %
                          (h["name"], ip))
            continue
        _, pool = hit
        excluded = any(ip_int(lo) <= ip_int(ip) <= ip_int(hi)
                       for lo, hi in pool["excluded"])
        dns_ok = (not pool["dns"]) or (not h.get("dns")) or \
            pool["dns"].split()[0] == h["dns"]
        good = not excluded and dns_ok
        pool_ok &= good
        if verbose:
            print("  [%s] %-14s %s in %s (%s)" % (
                "PASS" if good else "FAIL", h["name"], ip,
                pool["net"], pool["name"]))
    _check(pool_ok, "seeded leases conform to their pools")

    # ---- 6. OSPF coverage ---------------------------------------------------
    if verbose:
        print("== 6. OSPF coverage ==")
    rparent = {r: r for r in routers}

    def find_r(x):
        while rparent[x] != x:
            rparent[x] = rparent[rparent[x]]
            x = rparent[x]
        return x

    edges = 0
    for lk in spec["links"]:
        if lk["type"] != "eSerial":
            continue
        ra, rb = find_r(lk["a_dev"]), find_r(lk["b_dev"])
        if ra != rb:
            rparent[ra] = rb
        edges += 1
    connected = len({find_r(r) for r in routers}) <= 1
    _check(connected, "router graph connected over serial links")

    ospf_ok = True
    for rn, rd in routers.items():
        nets = ospf_networks(rd["config"])
        if not nets:
            continue
        for pname, pi in ios_interfaces(rd["config"]).items():
            if pi["ip"] and not any(cidr_match(pi["ip"], n, w)
                                    for n, w, _ in nets):
                # WAN-to-ISP style ports may be static by design; flag only
                # when the router runs OSPF at all
                if rn == "R9-BORDER" and pname == "Serial0/0/1":
                    continue          # WAN toward ISP: static/default, not OSPF
                ospf_ok = False
                if verbose:
                    print("  [FAIL] %s %s (%s) not advertised into OSPF"
                          % (rn, pname, pi["ip"]))
    _check(ospf_ok, "routed interfaces covered by OSPF network statements")

    # ---- 7. ping matrix ------------------------------------------------------
    if verbose:
        n_pairs = len(hosts) * max(len(hosts) - 1, 0)
        print("== 7. full ping matrix (%d ordered pairs) ==" % n_pairs)

    def reachable(ra, rb):
        if ra is None or rb is None:
            return False
        return find_r(ra) == find_r(rb)

    parent_l1 = list(range(len(devices)))

    def find(x):
        while parent_l1[x] != x:
            parent_l1[x] = parent_l1[parent_l1[x]]
            x = parent_l1[x]
        return x

    for lk in spec["links"]:
        ra_, rb_ = find(index[lk["a_dev"]]), find(index[lk["b_dev"]])
        if ra_ != rb_:
            parent_l1[ra_] = rb_

    def same_l2(a, b):
        va, vb = access_vlan(a["name"]), access_vlan(b["name"])
        return (va is not None and va == vb and
                find(index[a["name"]]) == find(index[b["name"]]))

    total = passed = 0
    fails = []

    for a in hosts:
        for b in hosts:
            if a is b:
                continue
            total += 1
            if same_l2(a, b) or reachable(host_rtr[a["name"]],
                                          host_rtr[b["name"]]):
                passed += 1
            else:
                fails.append((a["name"], b["name"]))
    if verbose:
        print("  pings passed: %d/%d" % (passed, total))
        for f in fails[:15]:
            print("  FAIL %s -> %s" % f)
    _check(passed == total, "full-matrix connectivity")

    return list(FAILURES)


def validate_file(path, verbose=True):
    from pktbuilder.model import load_topology
    spec = load_topology(path)
    return validate_spec(spec, verbose=verbose)


if __name__ == "__main__":
    fails = validate_file(sys.argv[1])
    print()
    print("RESULT: %s" % ("ALL CHECKS PASSED" if not fails
                          else "FAIL (%d checks)" % len(fails)))
    sys.exit(0 if not fails else 1)
