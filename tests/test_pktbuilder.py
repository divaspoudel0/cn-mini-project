# -*- coding: utf-8 -*-
"""Tests for pktbuilder."""

import os
import sys
import tempfile
import textwrap

TEST_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TEST_ROOT))

import pytest


def test_model_tiny_lab():
    from pktbuilder.model import load_topology, TopologyError
    spec = load_topology(os.path.join(TEST_ROOT, "..", "topologies", "tiny-lab.yaml"))
    assert spec["name"] == "tiny-lab"
    assert len(spec["devices"]) == 4
    assert len(spec["links"]) == 3


def test_model_rejects_duplicate_device_names():
    from pktbuilder.model import validate_spec, TopologyError
    with pytest.raises(TopologyError, match="duplicate device name"):
        validate_spec({
            "name": "bad",
            "devices": [
                {"name": "R1", "kind": "router", 
                 "config": "enable\nconfigure terminal\ninterface GigabitEthernet0/0\n ip address 10.0.0.1 255.255.255.0\nno shutdown"},
                {"name": "R1", "kind": "router", 
                 "config": "enable\nconfigure terminal\ninterface GigabitEthernet0/0\n ip address 10.0.0.2 255.255.255.0\nno shutdown"},
            ],
            "links": [],
        })


def test_model_rejects_invalid_kind():
    from pktbuilder.model import validate_spec, TopologyError
    with pytest.raises(TopologyError, match="kind must be one of"):
        validate_spec({
            "name": "bad",
            "devices": [{"name": "X", "kind": "firewall", "config": ""}],
            "links": [],
        })


def test_model_rejects_pc_with_partial_address():
    from pktbuilder.model import validate_spec, TopologyError
    with pytest.raises(TopologyError, match="missing"):
        validate_spec({
            "name": "bad",
            "devices": [{
                "name": "PC1", "kind": "pc",
                "ip": "10.0.0.1", "mask": "255.255.255.0",  # no gateway
            }],
            "links": [],
        })


def test_model_rejects_noncontiguous_mask():
    from pktbuilder.model import validate_spec, TopologyError
    with pytest.raises(TopologyError, match="not contiguous"):
        validate_spec({
            "name": "bad",
            "devices": [{
                "name": "PC1", "kind": "pc",
                "ip": "10.0.0.1", "mask": "255.0.255.0", "gateway": "10.0.0.1",
            }],
            "links": [],
        })


def test_model_rejects_serial_on_non_router():
    from pktbuilder.model import validate_spec, TopologyError
    with pytest.raises(TopologyError, match="serial cable needs Serial ports on BOTH ends"):
        validate_spec({
            "name": "bad",
            "devices": [
                {"name": "R1", "kind": "router", 
                 "config": "enable\nconfigure terminal\ninterface Serial0/0/0\n ip address 10.0.0.1 255.255.255.252\nno shutdown"},
                {"name": "PC1", "kind": "pc", 
                 "ip": "10.0.0.2", "mask": "255.255.255.252", "gateway": "10.0.0.1"},
            ],
            "links": [["R1", "Serial0/0/0", "PC1", "FastEthernet0"]],
        })


def test_model_rejects_copper_between_routers():
    from pktbuilder.model import validate_spec, TopologyError
    with pytest.raises(TopologyError, match="copper.*use a Serial link"):
        validate_spec({
            "name": "bad",
            "devices": [
                {"name": "R1", "kind": "router", 
                 "config": "enable\nconfigure terminal\ninterface GigabitEthernet0/0\n ip address 10.0.0.1 255.255.255.252\nno shutdown"},
                {"name": "R2", "kind": "router", 
                 "config": "enable\nconfigure terminal\ninterface GigabitEthernet0/0\n ip address 10.0.0.2 255.255.255.252\nno shutdown"},
            ],
            "links": [["R1", "GigabitEthernet0/0", "R2", "GigabitEthernet0/0"]],
        })


def test_model_validator_full():
    """Validate all three example topologies cleanly."""
    from pktbuilder.validator import validate_file
    for fn in ("tiny-lab.yaml", "campus-basic.yaml", "pmun.yaml"):
        path = os.path.join(TEST_ROOT, "..", "topologies", fn)
        fails = validate_file(path, verbose=False)
        assert not fails, f"{fn}: {fails}"


def test_builder_roundtrip_tiny():
    from pktbuilder.builder import build_topology
    from pktbuilder.pka2xml import decrypt_pka
    with tempfile.TemporaryDirectory() as td:
        xml, pkt = build_topology(
            os.path.join(TEST_ROOT, "..", "topologies", "tiny-lab.yaml"),
            outdir=td)
        assert pkt and os.path.exists(pkt)
        back = decrypt_pka(open(pkt, "rb").read())
        assert back == xml.encode("utf-8")
        # basic XML structure checks
        assert "<PACKETTRACER5" in xml
        assert "<DEVICES>" in xml and "</DEVICES>" in xml
        assert "<LINKS>" in xml and "</LINKS>" in xml
        assert "R1" in xml and "R2" in xml


def test_builder_campus_basic():
    from pktbuilder.builder import build_topology
    from pktbuilder.pka2xml import decrypt_pka
    with tempfile.TemporaryDirectory() as td:
        xml, pkt = build_topology(
            os.path.join(TEST_ROOT, "..", "topologies", "campus-basic.yaml"),
            outdir=td)
        assert pkt and os.path.exists(pkt)
        back = decrypt_pka(open(pkt, "rb").read())
        assert back == xml.encode("utf-8")
        # VLAN configs rendered
        assert "encapsulation dot1Q 10" in xml
        assert "STAFF-POOL" in xml


def test_builder_pmun():
    from pktbuilder.builder import build_topology
    from pktbuilder.pka2xml import decrypt_pka
    with tempfile.TemporaryDirectory() as td:
        xml, pkt = build_topology(
            os.path.join(TEST_ROOT, "..", "topologies", "pmun.yaml"),
            outdir=td)
        assert pkt and os.path.exists(pkt)
        back = decrypt_pka(open(pkt, "rb").read())
        assert back == xml.encode("utf-8")
        assert xml.count("<DEVICE>") == 32
        assert "ADMIN-PC" in xml and "R1-CORE" in xml


def test_cli_example():
    import subprocess
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "tiny-lab.yaml")
        res = subprocess.run(
            [sys.executable, "-m", "pktbuilder.cli", "example", "tiny-lab"],
            cwd=td, capture_output=True, text=True)
        assert res.returncode == 0
        assert os.path.exists(out)
        with open(out) as fh:
            txt = fh.read()
        assert "tiny-lab" in txt
        assert "PC1" in txt


def test_cli_decrypt_roundtrip():
    import subprocess
    with tempfile.TemporaryDirectory() as td:
        # build a packet first
        res = subprocess.run(
            [sys.executable, "-m", "pktbuilder.cli", "build",
             os.path.join(TEST_ROOT, "..", "topologies", "tiny-lab.yaml"),
             "-o", td],
            capture_output=True, text=True)
        assert res.returncode == 0
        pkt_path = os.path.join(td, "tiny-lab.pkt")
        # decrypt
        res2 = subprocess.run(
            [sys.executable, "-m", "pktbuilder.cli", "decrypt", pkt_path, "-o",
             os.path.join(td, "dec.xml")],
            capture_output=True, text=True)
        assert res2.returncode == 0
        assert os.path.exists(os.path.join(td, "dec.xml"))


def test_cli_validate_tiny():
    import subprocess
    res = subprocess.run(
        [sys.executable, "-m", "pktbuilder.cli", "validate",
         os.path.join(TEST_ROOT, "..", "topologies", "tiny-lab.yaml")],
        capture_output=True, text=True)
    assert res.returncode == 0
    assert "ALL CHECKS PASSED" in res.stdout


def test_cli_validate_pmun():
    import subprocess
    res = subprocess.run(
        [sys.executable, "-m", "pktbuilder.cli", "validate",
         os.path.join(TEST_ROOT, "..", "topologies", "pmun.yaml")],
        capture_output=True, text=True)
    assert res.returncode == 0
    assert "ALL CHECKS PASSED" in res.stdout


def test_example_unknown():
    import subprocess
    with tempfile.TemporaryDirectory() as td:
        res = subprocess.run(
            [sys.executable, "-m", "pktbuilder.cli", "example", "nope"],
            cwd=td, capture_output=True, text=True)
        assert res.returncode != 0
        assert "invalid choice" in res.stderr


if __name__ == "__main__":
    pytest.main([__file__, "-v"])