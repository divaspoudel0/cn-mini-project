#!/usr/bin/env python3
"""Build the PMUN (Pulchowk Metropolitan University Network) topology to XML/.pkt.

Consumes:
  - blueprints/*.device.xml   : ENGINE fragments from real Packet Tracer saves
                                (2911 router, 2960-24TT switch, PC-PT, Server-PT)
  - blueprints/skeleton.xml    : a full PACKETTRACER5 shell (OPTIONS, SCENARIOSET,
                                FILTERS, CLUSTERS, PHYSICALWORKSPACE; DEVICES/LINKS
                                emptied) so the emitter only fills those sections.
  - device-configs/*.txt       : per-device IOS CLI config - the source of truth
                                for hostname / interfaces / OSPF / DHCP pools.

Produces:
  - pmun_topology.pkt   (encrypted Packet Tracer file, via pka2xml.encrypt_pka)
  - pmun_topology.xml   (same document unencrypted, for inspection / round-trip)

Usage:
  python3 pktgen.py [outdir [pka2xml_dir]]

All device geometry lives in topology(); the rest is boilerplate.
"""

import ipaddress
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BP = os.path.join(HERE, "blueprints")
CFG = os.path.join(HERE, "..", "device-configs")

R2911_BP = os.path.join(BP, "r2911.device.xml")
SW2960_BP = os.path.join(BP, "sw2960.device.xml")
PC_BP = os.path.join(BP, "pc.device.xml")
SERVER_BP = os.path.join(BP, "server.device.xml")
SKELETON_BP = os.path.join(BP, "skeleton.xml")

WIC_MODEL = "WIC-2T"            # PT saves show both "WIC-2T" and "HWIC-2T"
GHOST_SLOT = ("        <SLOT>\n"
              "         <TYPE>eInterfaceCard</TYPE>\n"
              "        </SLOT>")


def read(path):
    return open(path, encoding="utf-8").read().strip()


def link_local(mac):
    """dotted aa.bb.cc.dd.ee.ff -> FE80::xxxx:xxxx:xxxx:xxxx (EUI-64)."""
    h = mac.replace(".", "")
    b = bytes(int(h[i:i + 2], 16) for i in range(0, 12, 2))
    ll = ((b[0] ^ 0x02) << 8) | b[1]
    return "FE80::%02x%02x:%02x%02x:%02x%02x" % (
        ll >> 8, ll & 0xff, b[2], b[3], b[4], b[5])


# ---------------------------------------------------------------------------
# IOS config introspection
# ---------------------------------------------------------------------------

def parse_intf_config(config):
    out = {}
    cur = None
    rows = []
    for ln in config.splitlines():
        t = ln.strip()
        m = re.match(r"^interface ([\w\./:]+)\s*$", t)
        if m:
            if cur is not None:
                out[cur] = _fold(rows)
            cur = m.group(1)
            rows = [t]
        elif cur is not None:
            rows.append(t)
    if cur is not None:
        out[cur] = _fold(rows)
    return out


def _fold(rows):
    d = {"ip": "", "mask": "", "clock": False}
    for r in rows:
        mm = re.match(r"^ip address (\S+) (\S+)", r)
        if mm:
            d["ip"], d["mask"] = mm.group(1), mm.group(2)
            continue
        if re.match(r"^clock rate", r):
            d["clock"] = True
    return d


def wic_count(ifaces):
    slots = set()
    for name in ifaces:
        m = re.match(r"^Serial0/(\d+)/\d+$", name)
        if m:
            slots.add(int(m.group(1)))
    return (max(slots) + 1) if slots else 0


# ---------------------------------------------------------------------------
# XML fragment builders
# ---------------------------------------------------------------------------

def set_name(xml, name):
    xml = re.sub(r'<NAME translate="true">[^<]*</NAME>',
                 '<NAME translate="true">%s</NAME>' % name, xml)
    xml = re.sub(r"<SYS_NAME>[^<]*</SYS_NAME>",
                 "<SYS_NAME>%s</SYS_NAME>" % name, xml)
    return xml


def set_physical(xml, name, kind):
    """Device WORKSPACE/PHYSICAL must name an existing node of the
    PHYSICALWORKSPACE tree: Intercity,...Wiring Closet,Table|Rack,<name>."""
    container = "Table" if kind == "pc" else "Rack"
    path = ("Intercity,Home City,Corporate Office,Main Wiring Closet,"
            "%s,%s") % (container, name)
    xml = re.sub(r'<PHYSICAL translate="true">[^<]*</PHYSICAL>',
                 '<PHYSICAL translate="true">%s</PHYSICAL>' % path, xml)
    return xml


def set_logical(xml, x, y, mem_addr=None, dev_addr=None):
    xml = re.sub(r"<X>[^<]*</X>\s*<Y>[^<]*</Y>",
                 "<X>%s</X>\n      <Y>%s</Y>" % (x, y), xml)
    if mem_addr is not None:
        xml = re.sub(r"<MEM_ADDR>[^<]*</MEM_ADDR>",
                     "<MEM_ADDR>%d</MEM_ADDR>" % mem_addr, xml)
    if dev_addr is not None:
        xml = re.sub(r"<DEV_ADDR>[^<]*</DEV_ADDR>",
                     "<DEV_ADDR>%d</DEV_ADDR>" % dev_addr, xml)
    return xml


def set_running(xml, config):
    lines = [ln.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             for ln in config.splitlines()]
    body = "\n".join("      <LINE>%s</LINE>" % ln for ln in lines)
    return re.sub(r"<RUNNINGCONFIG>.*?</RUNNINGCONFIG>",
                  "<RUNNINGCONFIG>\n%s\n     </RUNNINGCONFIG>" % body, xml,
                  flags=re.S)


# ---------------------------------------------------------------------------
# device builders
# ---------------------------------------------------------------------------

def serial_card(slot, ifaces, maca, macb):
    """One WIC-2T slot with two eSmartSerial ports (Serial0/<slot>/0 and /1)."""
    infoa = ifaces.get("Serial0/%d/0" % slot, {"mask": "", "clock": False})
    infob = ifaces.get("Serial0/%d/1" % slot, {"mask": "", "clock": False})
    porta = _serial_port(maca, infoa)
    portb = _serial_port(macb, infob)
    return (
        "        <SLOT>\n"
        "         <TYPE>eInterfaceCard</TYPE>\n"
        "         <MODULE>\n"
        "          <TYPE>eInterfaceCard</TYPE>\n"
        "          <MODEL>%s</MODEL>\n" % WIC_MODEL +
        porta + "\n" + portb + "\n" +
        "         </MODULE>\n"
        "        </SLOT>")


def _serial_port(mac, info):
    ll = link_local(mac)
    return (
        "          <PORT>\n"
        "           <TYPE>eSmartSerial</TYPE>\n"
        "           <POWER>true</POWER>\n"
        "           <PINS>false</PINS>\n"
        "           <BANDWIDTH>1544</BANDWIDTH>\n"
        "           <FULLDUPLEX>true</FULLDUPLEX>\n"
        "           <AUTONEGOTIATEBANDWIDTH>true</AUTONEGOTIATEBANDWIDTH>\n"
        "           <AUTONEGOTIATEDUPLEX>true</AUTONEGOTIATEDUPLEX>\n"
        "           <MACADDRESS>%s</MACADDRESS>\n"
        "           <BIA>%s</BIA>\n"
        "           <CLOCKRATE>64000</CLOCKRATE>\n"
        "           <CLOCKRATEFLAG>%s</CLOCKRATEFLAG>\n"
        "           <DESCRIPTION/>\n"
        "           <CHANNEL>0</CHANNEL>\n"
        "           <IP/>\n"
        "           <SUBNET/>\n"
        "           <PORT_GATEWAY/>\n"
        "           <PORT_DNS/>\n"
        "           <PORT_DHCP_ENABLE>false</PORT_DHCP_ENABLE>\n"
        "           <ND_SUPPRESSED>false</ND_SUPPRESSED>\n"
        "           <TIMEOUT>14400000</TIMEOUT>\n"
        "           <PC_FIREWALL>false</PC_FIREWALL>\n"
        "           <PC_IPV6_FIREWALL>false</PC_IPV6_FIREWALL>\n"
        "           <IPV6_ENABLED>false</IPV6_ENABLED>\n"
        "           <IPV6_ADDRESS_AUTOCONFIG>false</IPV6_ADDRESS_AUTOCONFIG>\n"
        "           <IPV6_PORT_GATEWAY/>\n"
        "           <IPV6_PORT_DNS/>\n"
        "           <IPV6_LINK_LOCAL>%s</IPV6_LINK_LOCAL>\n"
        "           <IPV6_DEFAULT_LINK_LOCAL>%s</IPV6_DEFAULT_LINK_LOCAL>\n"
        "           <IPV6_PORT_AUTO_CONFIG_ENABLED>false</IPV6_PORT_AUTO_CONFIG_ENABLED>\n"
        "           <IPV6_PORT_DHCP_ENABLED>false</IPV6_PORT_DHCP_ENABLED>\n"
        "           <IPV6_ADDRESSES/>\n"
        "          </PORT>" % (mac, mac, "true" if info["clock"] else "false", ll, ll))


def build_router(name, config, x, y, macgen, mem_addr, dev_addr):
    frag = read(R2911_BP)
    frag = set_name(frag, name)
    frag = set_physical(frag, name, "router")
    frag = set_logical(frag, x, y, mem_addr, dev_addr)
    frag = set_running(frag, config)
    ifaces = parse_intf_config(config)
    wic = wic_count(ifaces)
    if wic:
        cards = "\n".join(serial_card(slot, ifaces, macgen(), macgen())
                          for slot in range(wic))
        # put the cards into the first empty eInterfaceCard slot
        frag = frag.replace(GHOST_SLOT, cards, 1)
    return frag


def build_switch(name, config, x, y, mem_addr, dev_addr):
    frag = read(SW2960_BP)
    frag = set_name(frag, name)
    frag = set_physical(frag, name, "switch")
    frag = set_logical(frag, x, y, mem_addr, dev_addr)
    frag = set_running(frag, config)
    return frag


def build_host(dev, macgen, mem_addr, dev_addr):
    bp = SERVER_BP if dev["kind"] == "server" else PC_BP
    frag = read(bp)
    frag = set_name(frag, dev["name"])
    frag = set_physical(frag, dev["name"], dev["kind"])
    frag = set_logical(frag, dev["x"], dev["y"], mem_addr, dev_addr)
    frag = host_port_fill(frag, dev.get("ip", ""), dev.get("mask", ""),
                          dev.get("gw", ""), dev.get("dns", ""),
                          dev.get("dhcp", False))
    if dev["kind"] == "server" and dev.get("records"):
        frag = server_dns(frag, dev["records"])
    return frag


def host_port_fill(xml, ip, mask, gw, dns, dhcp):
    # blueprints carry empty `<TAG/>` forms; normalize to `<TAG></TAG>`
    def _norm(m):
        return "<%s></%s>" % (m.group(1), m.group(1))
    for tag in ("PORT_DHCP_ENABLE", "IP", "SUBNET", "PORT_GATEWAY",
                "PORT_DNS", "GATEWAY"):
        xml = re.sub(r"<(%s)\s*/>" % tag, _norm, xml)
    pat = r"(<PORT>\s*<TYPE>\s*eCopperFastEthernet\b.*?</PORT>)"
    def sub(m):
        p = m.group(1)
        p = re.sub(r"<PORT_DHCP_ENABLE>[^<]*</PORT_DHCP_ENABLE>",
                   "<PORT_DHCP_ENABLE>%s</PORT_DHCP_ENABLE>"
                   % ("true" if dhcp else "false"), p)
        if dhcp and not ip:
            # pure DHCP client: ship with empty address fields
            p = re.sub(r"<IP>[^<]*</IP>", "<IP/>", p)
            p = re.sub(r"<SUBNET>[^<]*</SUBNET>", "<SUBNET/>", p)
            p = re.sub(r"<PORT_GATEWAY>[^<]*</PORT_GATEWAY>", "<PORT_GATEWAY/>", p)
        else:
            # static config or a seeded DHCP lease (how a genuine PT save
            # looks after the client acquired its address from the pool)
            p = re.sub(r"<IP>[^<]*</IP>", "<IP>%s</IP>" % ip, p)
            p = re.sub(r"<SUBNET>[^<]*</SUBNET>", "<SUBNET>%s</SUBNET>" % mask, p)
            p = re.sub(r"<PORT_GATEWAY>[^<]*</PORT_GATEWAY>",
                       "<PORT_GATEWAY>%s</PORT_GATEWAY>" % gw, p)
        if dns:
            p = re.sub(r"<PORT_DNS>[^<]*</PORT_DNS>", "<PORT_DNS>%s</PORT_DNS>" % dns, p)
        return p
    xml, _ = re.subn(pat, sub, xml, count=1, flags=re.S)
    if gw:
        def _gw(m, _gw_val=gw):
            return m.group(1) + _gw_val + m.group(2)
        xml = re.sub(r"(<GATEWAY>)[^<]*(</GATEWAY>)", _gw, xml)
    return xml


def server_dns(xml, records):
    rows = "\n".join(
        "       <RESOURCE-RECORD>\n"
        "        <TYPE>A-REC</TYPE>\n"
        "        <NAME>%s</NAME>\n"
        "        <TTL>86400</TTL>\n"
        "        <IPADDRESS>%s</IPADDRESS>\n"
        "       </RESOURCE-RECORD>" % (nm, ip) for nm, ip in records)
    block = ("<DNS_SERVER>\n"
             "      <ENABLED>1</ENABLED>\n"
             "      <NAMESERVER-DATABASE>\n"
             "%s\n"
             "      </NAMESERVER-DATABASE>\n"
             "     </DNS_SERVER>" % rows)
    return re.sub(r"<DNS_SERVER>.*?</DNS_SERVER>", block, xml, flags=re.S)


def device_wrap(frag):
    return "   <DEVICE>\n%s\n   </DEVICE>" % frag


_dev_addr_counter = [0]
_port_addr_counter = [0]


def _addr_seq(counter, base):
    counter[0] += 1
    return base + counter[0]


def make_device_addrs():
    """Return (mem_addr, dev_addr) unique across all generated devices."""
    mem = _addr_seq(_dev_addr_counter, 100000000)
    dev = _addr_seq(_dev_addr_counter, 100000000)
    return mem, dev


def make_port_addrs():
    return (_addr_seq(_port_addr_counter, 200000000),
            _addr_seq(_port_addr_counter, 200000000))


# ---------------------------------------------------------------------------
# links
# ---------------------------------------------------------------------------

def serial_link(f, fport, t, tport, dce_idx, dce_name,
                fdev_addr, tdev_addr, fp, tp):
    return ("   <LINK>\n"
            "    <TYPE>eSerial</TYPE>\n"
            "    <CABLE>\n"
            "     <LENGTH>0</LENGTH>\n"
            "     <FROM>%d</FROM>\n"
            "     <PORT>%s</PORT>\n"
            "     <TO>%d</TO>\n"
            "     <PORT>%s</PORT>\n"
            "     <FROM_DEVICE_MEM_ADDR>%d</FROM_DEVICE_MEM_ADDR>\n"
            "     <TO_DEVICE_MEM_ADDR>%d</TO_DEVICE_MEM_ADDR>\n"
            "     <FROM_PORT_MEM_ADDR>%d</FROM_PORT_MEM_ADDR>\n"
            "     <TO_PORT_MEM_ADDR>%d</TO_PORT_MEM_ADDR>\n"
            "     <DCEDEV>%d</DCEDEV>\n"
            "     <DCEPORT>%s</DCEPORT>\n"
            "    </CABLE>\n"
            "   </LINK>" % (f, fport, t, tport, fdev_addr, tdev_addr,
                            fp, tp, dce_idx, dce_name))


def copper_link(f, fport, t, tport, fdev_addr, tdev_addr, fp, tp):
    return ("   <LINK>\n"
            "    <TYPE>eCopper</TYPE>\n"
            "    <CABLE>\n"
            "     <LENGTH>0</LENGTH>\n"
            "     <FROM>%d</FROM>\n"
            "     <PORT>%s</PORT>\n"
            "     <TO>%d</TO>\n"
            "     <PORT>%s</PORT>\n"
            "     <FROM_DEVICE_MEM_ADDR>%d</FROM_DEVICE_MEM_ADDR>\n"
            "     <TO_DEVICE_MEM_ADDR>%d</TO_DEVICE_MEM_ADDR>\n"
            "     <FROM_PORT_MEM_ADDR>%d</FROM_PORT_MEM_ADDR>\n"
            "     <TO_PORT_MEM_ADDR>%d</TO_PORT_MEM_ADDR>\n"
            "     <TYPE>eStraightThrough</TYPE>\n"
            "    </CABLE>\n"
            "   </LINK>" % (f, fport, t, tport, fdev_addr, tdev_addr, fp, tp))


# ---------------------------------------------------------------------------
# topology
# ---------------------------------------------------------------------------

def def_device(name, kind, x=0, y=0, **kw):
    d = {"name": name, "kind": kind, "x": x, "y": y}
    d.update(kw)
    return d


def topology():
    """Build the concrete network and return (devices, links)."""
    devices = []
    index = {}

    def add(d):
        d["mem_addr"], d["dev_addr"] = make_device_addrs()
        index[d["name"]] = len(devices)
        devices.append(d)

    # ---- routers ----------------------------------------------------------
    # Layout: DMZ + ISP up top, AREA 0 backbone in the middle,
    # AREA 1 on the left, AREA 2 on the right -- devices are grouped by
    # OSPF area so the topology reads as three visually separate zones.
    for name, fname, x, y in (
            ("ISP-RTR", "ISP-RTR.txt", 680, 90),
            ("R9-BORDER", "R9-BORDER.txt", 360, 90),
            ("R1-CORE", "R1-CORE.txt", 200, 230),
            ("R2-DIST-A1", "R2-DIST-A1.txt", 90, 350),
            ("R3-DIST-A2", "R3-DIST-A2.txt", 310, 350),
            ("R4-ACC-ADMIN", "R4-ACC-ADMIN.txt", 40, 470),
            ("R5-ACC-FACULTY", "R5-ACC-FACULTY.txt", 150, 470),
            ("R6-ACC-STUDENT", "R6-ACC-STUDENT.txt", 260, 470),
            ("R7-ACC-ENG", "R7-ACC-ENG.txt", 420, 470),
            ("R8-ACC-HOSTEL", "R8-ACC-HOSTEL.txt", 520, 470),
            ("R10-ACC-BRANCH", "R10-ACC-BRANCH.txt", 470, 600),
    ):
        add({"name": name, "kind": "router", "config": _load_cfg(fname),
             "x": x, "y": y})

    # ---- switches ----------------------------------------------------------
    for name, fname, x, y in (
            ("SW-ADMIN", "SW-ADMIN.txt", 40, 570),
            ("SW-FACULTY", "SW-FACULTY.txt", 150, 570),
            ("SW-STUDENT", "SW-STUDENT.txt", 260, 570),
            ("SW-SERVICES", "SW-SERVICES.txt", 40, 670),
            ("SW-DMZ", "SW-DMZ.txt", 360, 200),
    ):
        add({"name": name, "kind": "switch", "config": _load_cfg(fname),
             "x": x, "y": y})

    # ---- hosts --------------------------------------------------------------
    hosts = [
        # name, kind, ip, mask, gw, dns, dhcp, x, y, records
        ("DNS-1", "server", "10.10.0.10", "255.255.255.224", "10.10.0.1",
         "10.10.0.10", False, 20, 750,
         [("dns.pmun.edu.np", "10.10.0.10"),
          ("www.pmun.edu.np", "10.10.0.11"),
          ("intranet.pmun.edu.np", "10.10.0.101"),
          ("mail.pmun.edu.np", "10.10.0.12")]),
        ("WEB-1", "server", "10.10.0.11", "255.255.255.224", "10.10.0.1",
         "10.10.0.10", False, 90, 750),
        ("MAIL-SERVER", "server", "10.10.0.12", "255.255.255.224", "10.10.0.1",
         "10.10.0.10", False, 160, 750),
        ("DNS-2", "server", "10.10.0.100", "255.255.255.224", "10.10.0.97",
         "10.10.0.10", False, 300, 290,
         [("dns.pmun.edu.np", "10.10.0.10"),
          ("www.pmun.edu.np", "10.10.0.11"),
          ("intranet.pmun.edu.np", "10.10.0.101"),
          ("mail.pmun.edu.np", "10.10.0.12")]),
        ("WEB-2", "server", "10.10.0.101", "255.255.255.224", "10.10.0.97",
         "10.10.0.10", False, 420, 290),
        ("ISP-DNS", "server", "198.51.100.2", "255.255.255.240", "198.51.100.1",
         "198.51.100.2", False, 680, 200, [("ns.isp.net", "198.51.100.2")]),
        # PCs: DHCP clients with seeded leases (ip/mask/gw/dns as acquired
        # from the matching router pool; leases sit outside excluded ranges)
        ("ADMIN-PC", "pc", "10.10.0.141", "255.255.255.128", "10.10.0.129",
         "10.10.0.10", True, 20, 640),
        ("ADMIN-PC2", "pc", "10.10.0.142", "255.255.255.128", "10.10.0.129",
         "10.10.0.10", True, 60, 640),
        ("ADMIN-PC3", "pc", "10.10.0.143", "255.255.255.128", "10.10.0.129",
         "10.10.0.10", True, 175, 640),
        ("FACULTY-PC", "pc", "10.10.1.11", "255.255.255.128", "10.10.1.1",
         "10.10.0.10", True, 130, 640),
        ("STUDENT-PC", "pc", "10.10.2.21", "255.255.255.0", "10.10.2.1",
         "10.10.0.10", True, 240, 640),
        ("STUDENT-PC2", "pc", "10.10.2.22", "255.255.255.0", "10.10.2.1",
         "10.10.0.10", True, 280, 640),
        ("LIBRARY-PC", "pc", "10.10.0.41", "255.255.255.224", "10.10.0.33",
         "10.10.0.10", True, 90, 540),
        ("ENG-PC", "pc", "10.10.1.141", "255.255.255.192", "10.10.1.129",
         "10.10.0.10", True, 400, 560),
        ("HOSTEL-PC", "pc", "10.10.3.21", "255.255.255.0", "10.10.3.1",
         "10.10.0.10", True, 500, 560),
        ("BRANCH-PC", "pc", "10.10.0.71", "255.255.255.240", "10.10.0.65",
         "10.10.0.10", True, 450, 690),
    ]
    for h in hosts:
        rec = {
            "name": h[0], "kind": h[1], "ip": h[2], "mask": h[3], "gw": h[4],
            "dns": h[5], "dhcp": h[6], "x": h[7], "y": h[8],
        }
        if len(h) > 9 and h[9]:
            rec["records"] = h[9]
        add(rec)

    # ---- serial point-to-point ----------------------------------------------
    serial = [
        # (deviceA, serialA, deviceB, serialB)  -- DCE side carries the clock
        ("ISP-RTR", "Serial0/0/0", "R9-BORDER", "Serial0/0/1"),
        ("R9-BORDER", "Serial0/0/0", "R1-CORE", "Serial0/1/0"),
        ("R1-CORE", "Serial0/0/0", "R2-DIST-A1", "Serial0/0/0"),
        ("R1-CORE", "Serial0/0/1", "R3-DIST-A2", "Serial0/0/1"),
        ("R2-DIST-A1", "Serial0/0/1", "R3-DIST-A2", "Serial0/0/0"),
        ("R2-DIST-A1", "Serial0/1/0", "R4-ACC-ADMIN", "Serial0/0/0"),
        ("R2-DIST-A1", "Serial0/1/1", "R5-ACC-FACULTY", "Serial0/0/0"),
        ("R2-DIST-A1", "Serial0/2/0", "R6-ACC-STUDENT", "Serial0/0/0"),
        ("R5-ACC-FACULTY", "Serial0/0/1", "R6-ACC-STUDENT", "Serial0/0/1"),
        ("R3-DIST-A2", "Serial0/1/0", "R7-ACC-ENG", "Serial0/0/0"),
        ("R3-DIST-A2", "Serial0/1/1", "R8-ACC-HOSTEL", "Serial0/0/0"),
        ("R7-ACC-ENG", "Serial0/0/1", "R10-ACC-BRANCH", "Serial0/0/0"),
        ("R8-ACC-HOSTEL", "Serial0/0/1", "R10-ACC-BRANCH", "Serial0/0/1"),
    ]
    # determine which endpoint is DCE (the side that has `clock rate`)
    dce = {}
    for d in devices:
        if d["kind"] != "router":
            continue
        for name, info in parse_intf_config(d["config"]).items():
            if info["clock"]:
                dce[(d["name"], name)] = True

    serial_links = []
    for a, pa, b, pb in serial:
        fa, ta = devices[index[a]], devices[index[b]]
        fpa, tpa = make_port_addrs()
        a_is_dce = (a, pa) in dce
        if a_is_dce:
            serial_links.append(serial_link(index[a], pa, index[b], pb,
                                            index[a], pa,
                                            fa["dev_addr"], ta["dev_addr"],
                                            fpa, tpa))
        else:
            serial_links.append(serial_link(index[b], pb, index[a], pa,
                                            index[b], pb,
                                            ta["dev_addr"], fa["dev_addr"],
                                            tpa, fpa))

    # ---- copper --------------------------------------------------------------
    copper = [
        # access routers -> their switch
        ("R4-ACC-ADMIN", "GigabitEthernet0/0", "SW-ADMIN", "GigabitEthernet0/1"),
        ("R5-ACC-FACULTY", "GigabitEthernet0/0", "SW-FACULTY", "GigabitEthernet0/1"),
        ("R6-ACC-STUDENT", "GigabitEthernet0/0", "SW-STUDENT", "GigabitEthernet0/1"),
        # inter-switch trunks: all three switches carry VLANs 10/20/30
        ("SW-ADMIN", "GigabitEthernet0/2", "SW-FACULTY", "GigabitEthernet0/2"),
        ("SW-FACULTY", "FastEthernet0/21", "SW-STUDENT", "GigabitEthernet0/2"),
        # server farm (Area 1, R4)
        ("R4-ACC-ADMIN", "GigabitEthernet0/1", "SW-SERVICES", "GigabitEthernet0/1"),
        ("SW-SERVICES", "FastEthernet0/1", "DNS-1", "FastEthernet0"),
        ("SW-SERVICES", "FastEthernet0/2", "WEB-1", "FastEthernet0"),
        ("SW-SERVICES", "FastEthernet0/3", "MAIL-SERVER", "FastEthernet0"),
        # DMZ (Area 0, R9): DNS-2 + WEB-2 on the same DMZ-LAN segment
        ("R9-BORDER", "GigabitEthernet0/0", "SW-DMZ", "GigabitEthernet0/1"),
        ("SW-DMZ", "FastEthernet0/1", "DNS-2", "FastEthernet0"),
        ("SW-DMZ", "FastEthernet0/2", "WEB-2", "FastEthernet0"),
        # PCs
        ("R4-ACC-ADMIN", "GigabitEthernet0/2", "LIBRARY-PC", "FastEthernet0"),
        ("SW-ADMIN", "FastEthernet0/1", "ADMIN-PC", "FastEthernet0"),
        ("SW-ADMIN", "FastEthernet0/2", "ADMIN-PC2", "FastEthernet0"),
        ("SW-FACULTY", "FastEthernet0/1", "FACULTY-PC", "FastEthernet0"),
        ("SW-FACULTY", "FastEthernet0/24", "ADMIN-PC3", "FastEthernet0"),
        ("SW-STUDENT", "FastEthernet0/1", "STUDENT-PC", "FastEthernet0"),
        ("SW-STUDENT", "FastEthernet0/2", "STUDENT-PC2", "FastEthernet0"),
        ("R7-ACC-ENG", "GigabitEthernet0/0", "ENG-PC", "FastEthernet0"),
        ("R8-ACC-HOSTEL", "GigabitEthernet0/0", "HOSTEL-PC", "FastEthernet0"),
        ("R10-ACC-BRANCH", "GigabitEthernet0/0", "BRANCH-PC", "FastEthernet0"),
        ("ISP-RTR", "GigabitEthernet0/0", "ISP-DNS", "FastEthernet0"),
    ]
    copper_links = []
    for a, pa, b, pb in copper:
        fa, ta = devices[index[a]], devices[index[b]]
        fpa, tpa = make_port_addrs()
        copper_links.append(copper_link(index[a], pa, index[b], pb,
                                        fa["dev_addr"], ta["dev_addr"],
                                        fpa, tpa))

    return devices, serial_links, copper_links


def _load_cfg(fname):
    return read(os.path.join(CFG, fname))


# ---------------------------------------------------------------------------
# physical workspace tree
# ---------------------------------------------------------------------------

def _node_block(xml, name):
    """Return (start,end) of the <NODE>...</NODE> whose <NAME> is `name`."""
    i = xml.find('<NAME translate="true">%s</NAME>' % name)
    if i < 0:
        return None, None
    start = xml.rfind('<NODE>', 0, i)
    depth = 0
    j = start
    while j < len(xml):
        n_open = xml.find('<NODE>', j)
        n_close = xml.find('</NODE>', j)
        nxt = min(x for x in (n_open, n_close) if x >= 0)
        if nxt == n_open:
            depth += 1
            j = n_open + len('<NODE>')
        else:
            depth -= 1
            j = n_close + len('</NODE>')
            if depth == 0:
                return start, j
    return None, None


_WS_DEVICE = (
    "            <NODE>\n"
    "             <X>%s</X>\n"
    "             <Y>%s</Y>\n"
    "             <TYPE>6</TYPE>\n"
    "             <NAME translate=\"true\">%s</NAME>\n"
    "             <SX>1</SX>\n"
    "             <SY>1</SY>\n"
    "             <W>0</W>\n"
    "             <H>0</H>\n"
    "             <PATH>../art/Background/grid_100x100.png</PATH>\n"
    "             <CHILDREN/>\n"
    "             <MANUAL_SCALING>false</MANUAL_SCALING>\n"
    "             <SCALED_PIXMAP_WIDTH>0</SCALED_PIXMAP_WIDTH>\n"
    "             <SCALED_PIXMAP_HEIGHT>0</SCALED_PIXMAP_HEIGHT>\n"
    "             <INIT_WIDTH>0</INIT_WIDTH>\n"
    "             <INIT_HEIGHT>0</INIT_HEIGHT>\n"
    "             <INIT_SX>1</INIT_SX>\n"
    "             <INIT_SY>0</INIT_SY>\n"
    "             <BG_TILED>false</BG_TILED>\n"
    "            </NODE>")


def _ws_container(ntype, cname, children):
    return ("            <NODE>\n"
            "             <X>0</X>\n"
            "             <Y>0</Y>\n"
            "             <TYPE>%s</TYPE>\n"
            "             <NAME translate=\"true\">%s</NAME>\n"
            "             <SX>1</SX>\n"
            "             <SY>1</SY>\n"
            "             <W>0</W>\n"
            "             <H>0</H>\n"
            "             <PATH>../art/Background/grid_100x100.png</PATH>\n"
            "             <CHILDREN>\n%s\n"
            "             </CHILDREN>\n"
            "             <MANUAL_SCALING>false</MANUAL_SCALING>\n"
            "             <SCALED_PIXMAP_WIDTH>0</SCALED_PIXMAP_WIDTH>\n"
            "             <SCALED_PIXMAP_HEIGHT>0</SCALED_PIXMAP_HEIGHT>\n"
            "             <INIT_WIDTH>0</INIT_WIDTH>\n"
            "             <INIT_HEIGHT>0</INIT_HEIGHT>\n"
            "             <INIT_SX>1</INIT_SX>\n"
            "             <INIT_SY>0</INIT_SY>\n"
            "             <BG_TILED>false</BG_TILED>\n"
            "            </NODE>" % (ntype, cname, children))


def build_workspace(xml, devices):
    """Rebuild the <PHYSICALWORKSPACE> device nodes from the device list so
    every device has a matching NODE (PT rejects files whose devices have no
    physical-workspace node). PCs hang on the Table, routers/switches/servers
    on the Rack."""
    pcs = [d for d in devices if d["kind"] == "pc"]
    racks = [d for d in devices if d["kind"] != "pc"]
    table = "\n".join(_WS_DEVICE % (i * 12, 0, d["name"])
                      for i, d in enumerate(pcs))
    rack = "\n".join(_WS_DEVICE % (i * 12, 0, d["name"])
                     for i, d in enumerate(racks))
    table_block = _ws_container(5, "Table", table)
    rack_block = _ws_container(4, "Rack", rack)

    s, e = _node_block(xml, "Table")
    if s is None:
        return xml
    xml = xml[:s] + table_block + xml[e:]
    s, e = _node_block(xml, "Rack")
    if s is None:
        return xml
    xml = xml[:s] + rack_block + xml[e:]
    return xml




def _notes_block():
    """Area/zone labels shown in the logical workspace. Uses the same NOTE
    element structure as genuine PT saves (uuid/X/Y/Z/TEXT/NOTECLUSTERID)."""
    import uuid
    labels = [
        (140, 190, "OSPF AREA 0 - BACKBONE (R1 R2 R3 R9)"),
        (30, 420, "OSPF AREA 1 (R2 R4 R5 R6)"),
        (410, 420, "OSPF AREA 2 (R3 R7 R8 R10)"),
        (300, 160, "DMZ-LAN 10.10.0.96/27 (DNS-2, WEB-2)"),
        (620, 50, "UPSTREAM ISP - static route only"),
        (20, 720, "SERVER FARM 10.10.0.0/27 (DNS-1, WEB-1, MAIL)"),
    ]
    parts = []
    for x, y, text in labels:
        parts.append(
            "    <NOTE uuid=\"{%s}\">\n"
            "     <X>%d</X>\n"
            "     <Y>%d</Y>\n"
            "     <Z>40000</Z>\n"
            "     <TEXT translate=\"true\">%s</TEXT>\n"
            "     <NOTECLUSTERID>1-1</NOTECLUSTERID>\n"
            "    </NOTE>" % (uuid.uuid4(), x, y, text))
    return "<NOTES>\n%s\n  </NOTES>" % "\n".join(parts)


def render(devices, serial_links, copper_links, macgen):
    parts = []
    for d in devices:
        if d["kind"] == "router":
            frag = build_router(d["name"], d["config"], d["x"], d["y"], macgen,
                                d["mem_addr"], d["dev_addr"])
        elif d["kind"] == "switch":
            frag = build_switch(d["name"], d["config"], d["x"], d["y"],
                                d["mem_addr"], d["dev_addr"])
        else:
            frag = build_host(d, macgen, d["mem_addr"], d["dev_addr"])
        parts.append(device_wrap(frag))
    devices_xml = "\n".join(parts)

    links_xml = "\n".join(serial_links + copper_links)

    skeleton = read(SKELETON_BP)
    # insert devices and links into their emptied containers
    skeleton = re.sub(r"(<DEVICES>\s*)(.*?)(\s*</DEVICES>)",
                      lambda m: m.group(1) + "\n" + devices_xml + "\n  " + m.group(3),
                      skeleton, flags=re.S)
    skeleton = re.sub(r"(<LINKS>\s*)(.*?)(\s*</LINKS>)",
                      lambda m: m.group(1) + "\n" + links_xml + "\n  " + m.group(3),
                      skeleton, flags=re.S)
    skeleton = build_workspace(skeleton, devices)
    skeleton = re.sub(r"<NOTES>.*?</NOTES>", _notes_block(), skeleton, flags=re.S)
    return skeleton


def macgen_factory():
    i = [0x0001]
    def _next():
        i[0] += 1
        return "0060.709D.%04X" % (i[0] & 0xFFFF)
    return _next


def main(outdir=".", twodir=None):
    os.makedirs(outdir, exist_ok=True)
    devices, serial_links, copper_links = topology()
    xml = render(devices, serial_links, copper_links, macgen_factory())

    xml_path = os.path.join(outdir, "pmun_topology.xml")
    open(xml_path, "w", encoding="utf-8").write(xml)

    # encrypt — pka2xml ships next to this script; fall back to /tmp copy
    if twodir is None:
        twodir = HERE if os.path.exists(
            os.path.join(HERE, "pka2xml.py")) else "/tmp/opencode/pka2xml"
    sys.path.insert(0, os.path.abspath(twodir))
    from pka2xml import encrypt_pka, decrypt_pka
    pkg = encrypt_pka(xml.encode("utf-8"))
    pkt_path = os.path.join(outdir, "pmun_topology.pkt")
    open(pkt_path, "wb").write(pkg)

    # round-trip
    back = decrypt_pka(pkg).decode("utf-8")
    print("wrote %s (%d devices, %d links)" % (pkt_path, len(devices), len(serial_links) + len(copper_links)))
    print("round-trip XML match: %s" % (back == xml))


if __name__ == "__main__":
    args = sys.argv[1:]
    out = args[0] if args else "."
    td = args[1] if len(args) > 1 else None
    main(out, td)