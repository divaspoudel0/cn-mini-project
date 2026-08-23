"""Render a validated topology spec into PACKETTRACER5 XML and .pkt bytes.

The heavy lifting (blueprint fragments, workspace tree, EAX sealing) is the
same proven pipeline pktgen.py used for the PMUN network; this module just
drives it from a user-written topology spec instead of hardcoded data.
"""

import ipaddress
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
BP = os.path.join(HERE, "blueprints")

R2911_BP = os.path.join(BP, "r2911.device.xml")
SW2960_BP = os.path.join(BP, "sw2960.device.xml")
PC_BP = os.path.join(BP, "pc.device.xml")
SERVER_BP = os.path.join(BP, "server.device.xml")
SKELETON_BP = os.path.join(BP, "skeleton.xml")

WIC_MODEL = "WIC-2T"
GHOST_SLOT = ("        <SLOT>\n"
              "         <TYPE>eInterfaceCard</TYPE>\n"
              "        </SLOT>")


def _read(path):
    return open(path, encoding="utf-8").read().strip()


# ---------------------------------------------------------------------------
# IOS config introspection (same as upstream pka2xml-era generator)
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


def link_local(mac):
    """dotted aa.bb.cc.dd.ee.ff -> FE80::xxxx:xxxx:xxxx:xxxx."""
    h = mac.replace(".", "")
    b = bytes(int(h[i:i + 2], 16) for i in range(0, 12, 2))
    ll = ((b[0] ^ 0x02) << 8) | b[1]
    return "FE80::%02x%02x:%02x%02x:%02x%02x" % (
        ll >> 8, ll & 0xff, b[2], b[3], b[4], b[5])


# ---------------------------------------------------------------------------
# fragment builders
# ---------------------------------------------------------------------------

def set_name(xml, name):
    xml = re.sub(r'<NAME translate="true">[^<]*</NAME>',
                 '<NAME translate="true">%s</NAME>' % name, xml)
    xml = re.sub(r"<SYS_NAME>[^<]*</SYS_NAME>",
                 "<SYS_NAME>%s</SYS_NAME>" % name, xml)
    return xml


def set_physical(xml, name, kind):
    container = "Table" if kind == "pc" else "Rack"
    path = ("Intercity,Home City,Corporate Office,Main Wiring Closet,"
            "%s,%s") % (container, name)
    return re.sub(r'<PHYSICAL translate="true">[^<]*</PHYSICAL>',
                  '<PHYSICAL translate="true">%s</PHYSICAL>' % path, xml)


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


def host_port_fill(xml, ip, mask, gw, dns, dhcp):
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
        # dhcp=True with values seeded == a lease the client already acquired
        seed = (not dhcp) or bool(ip)
        if not seed:
            p = re.sub(r"<IP>[^<]*</IP>", "<IP/>", p)
            p = re.sub(r"<SUBNET>[^<]*</SUBNET>", "<SUBNET/>", p)
            p = re.sub(r"<PORT_GATEWAY>[^<]*</PORT_GATEWAY>",
                       "<PORT_GATEWAY/>", p)
        else:
            p = re.sub(r"<IP>[^<]*</IP>", "<IP>%s</IP>" % ip, p)
            p = re.sub(r"<SUBNET>[^<]*</SUBNET>", "<SUBNET>%s</SUBNET>" % mask,
                       p)
            p = re.sub(r"<PORT_GATEWAY>[^<]*</PORT_GATEWAY>",
                       "<PORT_GATEWAY>%s</PORT_GATEWAY>" % gw, p)
        if dns:
            p = re.sub(r"<PORT_DNS>[^<]*</PORT_DNS>",
                       "<PORT_DNS>%s</PORT_DNS>" % dns, p)
        return p

    xml, n = re.subn(pat, sub, xml, count=1, flags=re.S)
    if gw:
        xml = re.sub(r"(<GATEWAY>)[^<]*(</GATEWAY>)",
                     lambda m: m.group(1) + gw + m.group(2), xml)
    return xml


def server_dns(xml, records):
    rows = "\n".join(
        "       <RESOURCE-RECORD>\n"
        "        <TYPE>A-REC</TYPE>\n"
        "        <NAME>%s</NAME>\n"
        "        <TTL>86400</TTL>\n"
        "        <IPADDRESS>%s</IPADDRESS>\n"
        "       </RESOURCE-RECORD>" % (nm, ipaddr) for nm, ipaddr in records)
    block = ("<DNS_SERVER>\n"
             "      <ENABLED>1</ENABLED>\n"
             "      <NAMESERVER-DATABASE>\n%s\n"
             "      </NAMESERVER-DATABASE>\n"
             "     </DNS_SERVER>" % rows)
    return re.sub(r"<DNS_SERVER>.*?</DNS_SERVER>", block, xml, flags=re.S)


def serial_card(slot, ifaces, maca, macb):
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
        "           <IPV6_PORT_AUTO_CONFIG_ENABLED>false"
        "</IPV6_PORT_AUTO_CONFIG_ENABLED>\n"
        "           <IPV6_PORT_DHCP_ENABLED>false</IPV6_PORT_DHCP_ENABLED>\n"
        "           <IPV6_ADDRESSES/>\n"
        "          </PORT>"
        % (mac, mac, "true" if info["clock"] else "false", ll, ll))


def build_router(name, config, x, y, macgen, mem_addr, dev_addr):
    frag = _read(R2911_BP)
    frag = set_name(frag, name)
    frag = set_physical(frag, name, "router")
    frag = set_logical(frag, x, y, mem_addr, dev_addr)
    frag = set_running(frag, config)
    ifaces = parse_intf_config(config)
    wic = wic_count(ifaces)
    if wic:
        cards = "\n".join(serial_card(slot, ifaces, macgen(), macgen())
                          for slot in range(wic))
        frag = frag.replace(GHOST_SLOT, cards, 1)
    return frag


def build_switch(name, config, x, y, mem_addr, dev_addr):
    frag = _read(SW2960_BP)
    frag = set_name(frag, name)
    frag = set_physical(frag, name, "switch")
    frag = set_logical(frag, x, y, mem_addr, dev_addr)
    frag = set_running(frag, config)
    return frag


def build_host(dev, macgen, mem_addr, dev_addr):
    bp = SERVER_BP if dev["kind"] == "server" else PC_BP
    frag = _read(bp)
    frag = set_name(frag, dev["name"])
    frag = set_physical(frag, dev["name"], dev["kind"])
    frag = set_logical(frag, dev["x"], dev["y"], mem_addr, dev_addr)
    frag = host_port_fill(frag, dev.get("ip", ""), dev.get("mask", ""),
                          dev.get("gw", ""), dev.get("dns", ""),
                          dev.get("dhcp", False))
    if dev["kind"] == "server" and dev.get("records"):
        frag = server_dns(frag, dev["records"])
    return frag


# ---------------------------------------------------------------------------
# links / addressing counters
# ---------------------------------------------------------------------------

class _Counters:
    """Deterministic per-build address space (PT uses these as object ids)."""

    def __init__(self):
        self.device = 100000000
        self.port = 200000000

    def device_pair(self):
        self.device += 1
        mem = self.device
        self.device += 1
        return mem, self.device

    def port_pair(self):
        self.port += 1
        a = self.port
        self.device += 0          # keep streams independent
        self.port += 1
        return a, self.port


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
            "   </LINK>" % (f, fport, t, tport, fdev_addr, tdev_addr,
                            fp, tp))


# ---------------------------------------------------------------------------
# physical workspace + notes
# ---------------------------------------------------------------------------

def _node_block(xml, name):
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
    '             <NAME translate="true">%s</NAME>\n'
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
            '             <NAME translate="true">%s</NAME>\n'
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
    pcs = [d for d in devices if d["kind"] == "pc"]
    racks = [d for d in devices if d["kind"] != "pc"]
    table = "\n".join(_WS_DEVICE % (i * 12, 0, d["name"])
                      for i, d in enumerate(pcs))
    rack = "\n".join(_WS_DEVICE % (i * 12, 0, d["name"])
                     for i, d in enumerate(racks))
    s, e = _node_block(xml, "Table")
    if s is None:
        return xml
    xml = xml[:s] + _ws_container(5, "Table", table) + xml[e:]
    s, e = _node_block(xml, "Rack")
    if s is None:
        return xml
    xml = xml[:s] + _ws_container(4, "Rack", rack) + xml[e:]
    return xml


def notes_block(notes):
    import uuid
    parts = []
    for note in notes:
        parts.append(
            '    <NOTE uuid="{%s}">\n'
            "     <X>%d</X>\n"
            "     <Y>%d</Y>\n"
            "     <Z>40000</Z>\n"
            '     <TEXT translate="true">%s</TEXT>\n'
            "     <NOTECLUSTERID>1-1</NOTECLUSTERID>\n"
            "    </NOTE>" % (uuid.uuid4(), note["x"], note["y"],
                             _esc(note["text"])))
    body = "\n".join(parts)
    return "<NOTES>\n%s\n  </NOTES>" % body if parts else "<NOTES>\n  </NOTES>"


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


# ---------------------------------------------------------------------------
# top-level render
# ---------------------------------------------------------------------------

def render(spec):
    """spec (validated dict from model.validate_spec) -> full PT XML string."""
    devices_in = spec["devices"]
    index = spec["device_index"]
    counters = _Counters()

    class _MacGen:
        def __init__(self):
            self.n = 0x0001

        def __call__(self):
            self.n += 1
            return "0060.709D.%04X" % (self.n & 0xFFFF)

    macgen = _MacGen()

    devices = []
    for raw in devices_in:
        d = dict(raw)
        d["mem_addr"], d["dev_addr"] = counters.device_pair()
        devices.append(d)

    dce = {}
    for d in devices:
        if d["kind"] != "router":
            continue
        for name, info in parse_intf_config(d["config"]).items():
            if info["clock"]:
                dce[(d["name"], name)] = True

    serial_xml = []
    copper_xml = []
    for lk in spec["links"]:
        fa = devices[index[lk["a_dev"]]]
        ta = devices[index[lk["b_dev"]]]
        fpa, tpa = counters.port_pair()
        if lk["type"] == "eSerial":
            a_is_dce = (lk["a_dev"], lk["a_port"]) in dce
            b_is_dce = (lk["b_dev"], lk["b_port"]) in dce
            if a_is_dce or not b_is_dce:      # default: A side owns clock
                serial_xml.append(serial_link(
                    index[lk["a_dev"]], lk["a_port"],
                    index[lk["b_dev"]], lk["b_port"],
                    index[lk["a_dev"]], lk["a_port"],
                    fa["dev_addr"], ta["dev_addr"], fpa, tpa))
            else:
                serial_xml.append(serial_link(
                    index[lk["b_dev"]], lk["b_port"],
                    index[lk["a_dev"]], lk["a_port"],
                    index[lk["b_dev"]], lk["b_port"],
                    ta["dev_addr"], fa["dev_addr"], tpa, fpa))
        else:
            copper_xml.append(copper_link(
                index[lk["a_dev"]], lk["a_port"],
                index[lk["b_dev"]], lk["b_port"],
                fa["dev_addr"], ta["dev_addr"], fpa, tpa))

    parts = []
    for d in devices:
        if d["kind"] == "router":
            frag = build_router(d["name"], d["config"], d["x"], d["y"],
                                macgen, d["mem_addr"], d["dev_addr"])
        elif d["kind"] == "switch":
            frag = build_switch(d["name"], d["config"], d["x"], d["y"],
                                d["mem_addr"], d["dev_addr"])
        else:
            frag = build_host(d, macgen, d["mem_addr"], d["dev_addr"])
        parts.append("   <DEVICE>\n%s\n   </DEVICE>" % frag)

    skeleton = _read(SKELETON_BP)
    skeleton = re.sub(r"(<DEVICES>\s*)(.*?)(\s*</DEVICES>)",
                      lambda m: m.group(1) + "\n" + "\n".join(parts) +
                      "\n  " + m.group(3),
                      skeleton, flags=re.S)
    skeleton = re.sub(r"(<LINKS>\s*)(.*?)(\s*</LINKS>)",
                      lambda m: m.group(1) + "\n" +
                      "\n".join(serial_xml + copper_xml) + "\n  " + m.group(3),
                      skeleton, flags=re.S)
    skeleton = build_workspace(skeleton, devices)
    skeleton = re.sub(r"<NOTES>.*?</NOTES>", notes_block(spec["notes"]),
                      skeleton, flags=re.S)
    return skeleton


def build_topology(spec_or_path, outdir=".", encrypt=True):
    """Full pipeline: load -> validate -> render -> (encrypt) -> write files.

    Returns (xml_string, pkt_path or None).
    """
    from pktbuilder.model import load_topology
    from pktbuilder.pka2xml import encrypt_pka, decrypt_pka

    if isinstance(spec_or_path, str):
        spec = load_topology(spec_or_path)
    else:
        spec = spec_or_path

    xml = render(spec)
    os.makedirs(outdir, exist_ok=True)
    safe = re.sub(r"[^\w\-]+", "_", spec["name"]).strip("_") or "topology"
    xml_path = os.path.join(outdir, safe + ".xml")
    with open(xml_path, "w", encoding="utf-8") as fh:
        fh.write(xml)

    pkt_path = None
    if encrypt:
        pkt_path = os.path.join(outdir, safe + ".pkt")
        pkg = encrypt_pka(xml.encode("utf-8"))
        with open(pkt_path, "wb") as fh:
            fh.write(pkg)
        back = decrypt_pka(pkg)
        if back != xml.encode("utf-8"):
            raise RuntimeError("round-trip verification failed for "
                               + xml_path)
    return xml, pkt_path


# keep ipaddress import meaningful: used by validator, imported here so
# `python -c "import pktbuilder.builder"` surfaces missing deps early
_ = ipaddress
