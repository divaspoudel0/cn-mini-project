# Verification Checklist

Run these inside Packet Tracer (Realtime mode) before you submit. Each item maps to a specific
requirement — if it fails, that requirement isn't actually satisfied no matter what the config looks like.

## Connectivity
- [ ] Ping from a Student-LAN PC to a Server-Farm server (WEB-1) — proves inter-area OSPF routing works.
- [ ] Ping from Branch-Campus PC to Admin-LAN PC — proves the long path across Area 2 → Area 0 → Area 1 works.
- [ ] `traceroute` from a Hostel PC to WEB-2 (DMZ) — inspect the path, confirm it's sane (goes via R8→R3→R1→R9, not looping).

## Redundancy (multiple paths requirement)
- [ ] Shut down the R1–R2 serial link. Confirm OSPF reconverges and Admin-LAN can still reach Student-LAN
      (via R1–R3–R2, the triangle's alternate path). Re-enable the link afterward.
- [ ] Shut down R7–R10. Confirm Branch-Campus still reaches the core via R8–R10. Re-enable afterward.
- [ ] Take a screenshot of `show ip ospf neighbor` before/after each shutdown — good evidence for the report/viva.

## OSPF correctness
- [ ] `show ip ospf interface brief` on every router — confirm each interface is in the area you intended.
- [ ] `show ip route ospf` on an Area 1 router — confirm it has routes to Area 2 subnets (via R2→R1→R3, proving inter-area routing, not just intra-area).
- [ ] On R9: `show ip route` — confirm the `S*` default route exists and is being advertised (`show ip ospf database` should list it as a Type-5 or default external LSA).
- [ ] Confirm `ISP-RTR` has **no** OSPF process running (`show ip protocols` should show nothing, or explicitly confirm no neighbor relationship exists between R9 and ISP-RTR beyond the static routes).

## VLANs
- [ ] From ADMIN-PC on SW-ADMIN, ping ADMIN-PC3 on SW-FACULTY (both VLAN 10, different physical switch,
      connected via the SW-ADMIN↔SW-FACULTY trunk) — the actual proof that VLAN 10 "extends across switches."
- [ ] On each of SW-ADMIN / SW-FACULTY / SW-STUDENT: `show vlan` lists VLANs 10, 20, 30 and `show
      interfaces trunk` shows the inter-switch trunks carrying them — all three VLANs are trunked across
      all three switches.
- [ ] Confirm a Faculty-LAN PC (VLAN 20) **cannot** ping directly into VLAN 10 without going through R4/R5's
      routing — VLANs should be isolated at Layer 2, only reachable via inter-VLAN routing. If it works
      at Layer 2 without hitting a router, your trunk/access config is wrong somewhere.

## DNS / Web / DHCP
- [ ] From any PC, open a web browser (Desktop app) and load `http://www.pmun.edu.np` — should resolve
      via DNS-1/DNS-2 and load WEB-1's page.
- [ ] From a PC, `nslookup` something outside your domain (e.g. `google.com`) — DNS-1 should forward to
      ISP-DNS and (if you've added a fake record there for realism) resolve it.
- [ ] Check a freshly-added PC's IP Configuration tab shows an address from the correct pool, correct
      default gateway, and correct DNS server — all three, not just "got an IP."

## Documentation cross-check
- [ ] Every network ID in your topology diagram matches `02-network-design.md` exactly — a diagram/table
      mismatch is one of the easiest ways to lose marks in a viva.
- [ ] Header of the proposal document has full name and campus roll number (the assignment explicitly
      calls this out — trivial to lose marks over, don't skip it).
