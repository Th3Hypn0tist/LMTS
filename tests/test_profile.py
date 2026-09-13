from lmts.tools.profile import scan_system_profile


def test_profile_has_core_sections() -> None:
    profile = scan_system_profile().to_dict()
    assert set(profile) == {"cpu", "memory", "gpu", "npu", "software"}
    assert "logical_cores" in profile["cpu"]
    assert "total_bytes" in profile["memory"]
