"""pktbuild -- command line interface.

    pktbuild build     topol.yaml [-o DIR] [--xml-only]
    pktbuild validate  topol.yaml
    pktbuild example   NAME        write a starter topology (tiny-lab,
                                   campus-basic, pmun)
    pktbuild decrypt   FILE.pkt [-o out.xml]
"""

import argparse
import os
import shutil
import sys

EXAMPLES = ("tiny-lab", "campus-basic", "pmun")


def _examples_dir():
    # Try package data first, then fall back to source tree
    import pktbuilder
    pkg_dir = os.path.dirname(pktbuilder.__file__)
    candidate = os.path.join(pkg_dir, "topologies")
    if os.path.exists(candidate):
        return candidate
    # fallback for running from source tree
    return os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "topologies")


def cmd_build(args):
    from pktbuilder.builder import build_topology
    from pktbuilder.model import TopologyError
    try:
        xml, pkt = build_topology(args.topology, outdir=args.outdir,
                                  encrypt=not args.xml_only)
    except TopologyError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    name = os.path.basename(pkt or args.outdir)
    if pkt:
        print("wrote %s" % pkt)
    print("wrote %s" % os.path.join(
        args.outdir, os.path.splitext(name)[0] + ".xml"))
    print("round-trip verified: OK")
    return 0


def cmd_validate(args):
    from pktbuilder import validator
    from pktbuilder.model import TopologyError
    try:
        fails = validator.validate_file(args.topology, verbose=not args.quiet)
    except TopologyError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if not args.quiet:
        print()
    print("RESULT: %s" % ("ALL CHECKS PASSED" if not fails
                          else "FAIL (%d checks)" % len(fails)))
    return 0 if not fails else 1


def cmd_example(args):
    src = os.path.join(_examples_dir(), args.name + ".yaml")
    if not os.path.exists(src):
        print("unknown example %r (have: %s)"
              % (args.name, ", ".join(EXAMPLES)), file=sys.stderr)
        return 2
    dest = args.name + ".yaml"
    if os.path.exists(dest) and not args.force:
        print("%s already exists (use --force to overwrite)" % dest,
              file=sys.stderr)
        return 1
    # rewrite config_file references relative to the new location
    text = open(src, encoding="utf-8").read()
    base_src = _examples_dir()
    if args.name == "pmun":
        cfgdir = os.path.relpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "device-configs"),
            os.getcwd())
        text = text.replace("config_file: ../device-configs/",
                            "config_file: %s/" % cfgdir)
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(text)
    _ = base_src
    print("starter topology written to %s" % dest)
    print("next: pktbuild build %s -o output" % dest)
    return 0


def cmd_decrypt(args):
    from pktbuilder.pka2xml import decrypt_pka
    data = open(args.file, "rb").read()
    try:
        xml = decrypt_pka(data)
    except Exception as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    out = args.out or (os.path.splitext(args.file)[0] + ".xml")
    with open(out, "wb") as fh:
        fh.write(xml)
    print("decrypted %d bytes -> %s" % (len(xml), out))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="pktbuild",
        description="Generate Cisco Packet Tracer .pkt files from a "
                    "YAML/JSON topology description.")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="build .pkt (+.xml) from a topology")
    b.add_argument("topology", help="path to topology .yaml/.json")
    b.add_argument("-o", "--outdir", default="output",
                   help="output directory (default: ./output)")
    b.add_argument("--xml-only", action="store_true",
                   help="write the XML only; skip encryption")
    b.set_defaults(func=cmd_build)

    v = sub.add_parser("validate",
                       help="run all static checks on a topology")
    v.add_argument("topology", help="path to topology .yaml/.json")
    v.add_argument("-q", "--quiet", action="store_true",
                   help="print only the final verdict")
    v.set_defaults(func=cmd_validate)

    e = sub.add_parser("example", help="write a starter topology file")
    e.add_argument("name", nargs="?", default="tiny-lab",
                   choices=EXAMPLES, help="which starter (default tiny-lab)")
    e.add_argument("--force", action="store_true")
    e.set_defaults(func=cmd_example)

    d = sub.add_parser("decrypt", help="decrypt a .pkt/.pka back to XML")
    d.add_argument("file", help="path to .pkt or .pka")
    d.add_argument("-o", "--out", default=None, help="output XML path")
    d.set_defaults(func=cmd_decrypt)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
