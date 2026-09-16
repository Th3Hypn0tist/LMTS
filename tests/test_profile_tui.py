from lmts.view.tui_render import _reference_suite_lines


def test_reference_suite_lines_render_each_test_and_summary() -> None:
    suite = {
        "suite_version": 1,
        "tests": [
            {
                "benchmark_id": "lmts.reference.cpu.sha256_stream_1t",
                "label": "SHA-256 stream 1T",
                "method": "sha256_stream",
                "method_version": 1,
                "metrics": {"throughput_gib_per_second": 1.5},
            },
            {
                "benchmark_id": "lmts.reference.cpu.sha256_stream_all_threads",
                "label": "SHA-256 stream all threads",
                "method": "sha256_stream_parallel",
                "method_version": 1,
                "metrics": {"throughput_gib_per_second": 8.25},
            },
        ],
        "summary": {"parallel_scaling_factor": 5.5},
    }

    lines = _reference_suite_lines("CPU", suite)

    assert lines == [
        "CPU: v1",
        "  SHA-256 stream 1T: 1.50 GiB/s [sha256_stream v1]",
        "  SHA-256 stream all threads: 8.25 GiB/s [sha256_stream_parallel v1]",
        "  Parallel scaling: 5.50x",
    ]


def test_reference_suite_lines_show_unmeasured_domain() -> None:
    assert _reference_suite_lines("GPU", None) == ["GPU: not measured"]
