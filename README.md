# pktbuilder — Cisco Packet Tracer Topology Generator

Generate **version-compatible `.pkt` files** from a simple, human-readable **YAML** (or JSON) topology description. Write your network once — routers, switches, PCs, servers, VLANs, DHCP pools, OSPF areas, serial back-to-back links — and `pktbuild` produces a ready-to-open Packet Tracer file with every device pre-configured, tested, and verified.

```bash
# 1. Create a starter topology
pktbuild example tiny-lab

# 2. Edit the YAML to match your network
vim tiny-lab.yaml

# 3. Validate (addressing, VLAN domains, OSPF coverage, ping matrix)
pktbuild validate tiny-lab.yaml

# 4. Build the .pkt file
pktbuild build tiny-lab.yaml -o output
# → output/tiny-lab.pkt  (open in Packet Tracer)
```

---

## Why pktbuilder?

| Without `pktbuilder` | With `pktbuilder` |
|---------------------|-------------------|
| Click, drag, cable, type CLI in every device | Write one YAML file |
| Manual IP / VLAN / DHCP bookkeeping | Single source of truth |
| No way to verify before opening PT | `pktbuild validate` catches mistakes |
| Hard to version-control a `.pkt` binary | YAML diffs cleanly in Git |
| Re-creating a lab = hours of clicking | Re-creating = `pktbuild build` |

---

## Quick Start

### Install
```bash
git clone https://github.com/<your-org>/pktbuilder
cd pktbuilder
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

### Try the examples
```bash
# Three bundled starters
pktbuild example tiny-lab      # 2 routers, 1 serial, 2 PCs, OSPF
pktbuild example campus-basic  # 1 router-on-a-stick, 2 VLANs, DHCP, DNS
pktbuild example pmun          # Full 32-device campus (see below)

# Build & validate any of them
pktbuild validate tiny-lab.yaml
pktbuild build tiny-lab.yaml -o output
# open output/tiny-lab.pkt in Packet Tracer
```

---

## Topology File Format (YAML)

```yaml
name: my-campus          # used for output filename
notes:                   # optional workspace labels
  - {x: 100, y: 50, text: "OSPF Area 0"}
devices:
  - name: CORE-RTR
    kind: router         # router | switch | pc | server
    x: 250
    y: 120
    config: |            # inline IOS config (or use config_file:)
      enable
      configure terminal
      hostname CORE-RTR
      interface GigabitEthernet0/0
       ip address 10.0.0.1 255.255.255.252
       no shutdown
      router ospf 1
       network 10.0.0.0 0.0.0.3 area 0
      end
      write memory

  - name: EDGE-SW
    kind: switch
    x: 250
    y: 260
    config_file: configs/edge-sw.txt  # external file for big configs

  - name: ADMIN-PC
    kind: pc
    x: 80
    y: 300
    dhcp: true           # client will request via DHCP
    ip: 10.10.10.11      # SEED the acquired lease so PT opens configured
    mask: 255.255.255.0
    gateway: 10.10.10.1
    dns: 10.10.10.10

  - name: SRV-DNS
    kind: server
    ip: 10.10.10.10
    mask: 255.255.255.0
    gateway: 10.10.10.1
    dns_records:
      - [intranet.local, 10.10.10.10]
      - [www.local, 10.10.10.11]

links:
  # Serial back-to-back (DCE auto-detected from `clock rate`)
  - [CORE-RTR, Serial0/0/0, WAN-RTR, Serial0/0/0]

  # Copper (access / trunk / host)
  - [CORE-RTR, GigabitEthernet0/1, EDGE-SW, GigabitEthernet0/1]
  - [EDGE-SW, FastEthernet0/1, ADMIN-PC, FastEthernet0]
  - [EDGE-SW, FastEthernet0/24, SRV-DNS, FastEthernet0]
```

### Device Kinds

| Kind | Required fields | Notes |
|------|----------------|-------|
| `router` | `config` or `config_file` | IOS CLI; subinterfaces `G0/0.10` auto-wired |
| `switch` | `config` or `config_file` | 2960-24TT blueprint; `vlan`, `interface range` parsed |
| `pc` | `ip`+`mask`+`gateway` **or** `dhcp: true` | If `dhcp: true` + `ip` → PT save has the acquired lease |
| `server` | same as PC + optional `dns_records` | DNS server fragment injected |

### Links

* **Serial**: `[R1, Serial0/0/0, R2, Serial0/0/0]` — DCE end detected from `clock rate` in the config.
* **Copper**: `[SW1, GigabitEthernet0/1, R1, GigabitEthernet0/0]` — straight-through.
* Validation forbids copper between two routers, serial to non-routers, duplicate port usage.

---

## What Validation Checks (`pktbuild validate`)

1. **Host addressing** — every PC/server has a complete, unique IP plan (or DHCP).
2. **Gateways** — each gateway IP exists on a router interface sharing the host subnet.
3. **Serial subnets** — both ends of every serial link share one subnet.
4. **VLAN broadcast domains** — BFS through switches verifies every switched host reaches its gateway inside the correct VLAN.
5. **DHCP pool conformance** — seeded leases sit inside declared pools, outside excluded ranges, with matching DNS/default-router.
6. **OSPF coverage** — router graph connected via serial; every routed interface advertised (WAN-to-ISP static ports exempt).
7. **Full ping matrix** — simulates every ordered host pair; 100 % reachability expected.

---

## CLI Reference

```
pktbuild build     TOPOLOGY.yaml [-o DIR] [--xml-only]
pktbuild validate  TOPOLOGY.yaml [-q]
pktbuild example   NAME [--force]           # NAME: tiny-lab | campus-basic | pmun
pktbuild decrypt   FILE.pkt [-o OUT.xml]    # inspect / diff any .pkt
```

* `--xml-only` skips encryption (useful for diffing XML directly).
* `-q` on validate prints only the final verdict.

---

## Example: PMUN (Pulchowk Metropolitan University Network)

The bundled `pmun.yaml` reproduces the 32-device campus network from the original packet-builder project:

* **Routers (11)**: ISP border, core, distribution, 8 access routers across 3 OSPF areas
* **Switches (5)**: Admin, Faculty, Student (VLANs 10/20/30 trunked), Services, DMZ
* **Servers (4)**: DNS-1/WEB-1/MAIL in server farm; DNS-2/WEB-2 in DMZ; ISP-DNS upstream
* **PCs (10)**: DHCP clients with pre-seeded leases across 8 pools
* **Serial links (13)**: Full backbone + redistribution; DCE clocks in configs

```bash
pktbuild example pmun       # writes pmun.yaml (refs ../device-configs/)
pktbuild validate pmun.yaml # ALL CHECKS PASSED
pktbuild build pmun.yaml -o output
# → output/pmun_topology.pkt  (open in Packet Tracer)
```

---

## Programmatic API

```python
from pktbuilder import load_topology, build_topology, encrypt_pka, decrypt_pka

spec = load_topology("my-topo.yaml")      # validates
xml, pkt_path = build_topology(spec, outdir="out")  # .xml + .pkt

# or work with raw XML
xml_bytes = build_topology(spec, outdir="out", encrypt=False)[0].encode()
pkt_bytes = encrypt_pka(xml_bytes)        # EAX-sealed .pkt
xml_again = decrypt_pka(pkt_bytes)        # round-trip verified
```

---

## Project Layout

```
pktbuilder/
  blueprints/          # ENGINE fragments from real PT saves
  topologies/          # bundled example .yaml files
  __init__.py
  model.py             # YAML/JSON load + strict validation
  builder.py           # XML rendering from spec (blueprint-driven)
  validator.py         # static L2/L3 verification (no PT needed)
  cli.py               # pktbuild command
  pka2xml.py           # pure-Python EAX decrypt/encrypt (Crypto++-compatible)
tests/
  test_pktbuilder.py   # 16 tests: model, builder, CLI, round-trips
topologies/
  tiny-lab.yaml
  campus-basic.yaml
  pmun.yaml
pyproject.toml
README.md
```

---

## Extending

* **New device type**: add a blueprint `<name>.device.xml` to `blueprints/`, then a `build_<kind>` function in `builder.py`.
* **New port type**: extend `_PORTNAME` regex and `switch_ports()` in `model.py`.
* **Custom checks**: import `validator.validate_spec(spec)` and add your own rules.

---

## License

MIT — see `LICENSE` (or add one).

---

## Acknowledgements

* Packet Tracer file format reverse-engineered from Cisco's Crypto++ reference implementation.
* Blueprint fragments extracted from genuine PT saves (2911 router, 2960-24TT switch, PC-PT, Server-PT).
* Inspired by the PMUN (Pulchowk Metropolitan University Network) lab project.