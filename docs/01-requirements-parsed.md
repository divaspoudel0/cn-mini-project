# Requirements — Parsed Checklist

Source: IOE Pulchowk Campus, Computer Networks Mini-Project Proposal (July 2025 batch).

Use this file to grade the design in `02-network-design.md` against. Every box must map to something
concrete and named, not just "yes we did OSPF somewhere."

- [ ] **IP address block**: at least a /22 or larger. → Must state the exact block.
- [ ] **Networks**: minimum 9 networks (LANs, not counting router-to-router P2P links), with **at least
      6 different subnet sizes** among them.
- [ ] **VLANs**: at least 3 VLANs, extended across at least 3 different switches (i.e. trunked, same VLAN
      reachable from more than one switch).
- [ ] **Routers**: at least 9 routers total, of which **at least 3 have no LAN interface at all**
      (pure transit/backbone routers, only router-to-router links).
- [ ] **Routing protocol**: OSPF for all internal routing.
  - [ ] Default/Internet-bound traffic forwarded to the upstream ISP (static default route on the border
        router, redistributed into OSPF, or `default-information originate`).
  - [ ] The ISP forwards traffic *into* your network using a **static route** (not dynamic routing) —
        i.e. no OSPF/BGP peering with the ISP itself.
  - [ ] At least **3 OSPF areas**, including the backbone (Area 0).
  - [ ] Follow standard good practice: passive-interface on LAN-facing ports, router-id set explicitly,
        area boundaries at ABRs, no unnecessary route redistribution loops.
- [ ] **Servers**
  - [ ] At least 2 DNS servers, in different LANs, doing caching + resolving your own domain's web
        records.
  - [ ] At least 2 Web servers, on different subnets.
  - [ ] One more DNS server layer sitting inside the **upstream ISP's** network, used to resolve
        addresses beyond your own domain (simulates root/public DNS).
  - [ ] DHCP: each LAN *can* have a DHCP server (interpreted as: each LAN should hand out IP,
        default gateway, and DNS server info via DHCP — use one DHCP server per LAN or a
        centralized DHCP server with `ip helper-address`/relay per LAN, either is standard practice).
- [ ] **Topology**: multiple paths (redundant links) in **at least 2** of the networks/areas.
- [ ] **Header**: full name + campus roll number on the proposal document header.

## Deliverables required in the proposal
1. **Topology diagram** showing:
   - All routers, switches, PCs, servers.
   - The link to the upstream ISP.
   - Network ID of every network — LAN **and** point-to-point link.
   - Location + description of web and DNS servers.
   - Location of DHCP server(s).
2. **Written description** containing:
   - Pool of IP addresses (the overall block).
   - A table of subnets: size, IP range, network ID.
   - IP address of every server.
   - Any additional specs.
