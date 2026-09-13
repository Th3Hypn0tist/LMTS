from __future__ import annotations

import ctypes
import ctypes.util
import statistics
import time
from dataclasses import dataclass
from typing import Any


class CudaUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CudaDeviceIdentity:
    index: int
    name: str
    uuid: str | None
    total_memory_bytes: int | None

    def target(self) -> dict[str, object]:
        return {
            "device_index": self.index,
            "vendor": "NVIDIA",
            "model": self.name,
            "uuid": self.uuid,
        }


class CudaDriver:
    def __init__(self) -> None:
        names = [ctypes.util.find_library("cuda"), "libcuda.so.1", "nvcuda.dll"]
        self.lib = None
        for name in names:
            if not name:
                continue
            try:
                self.lib = ctypes.CDLL(name)
                break
            except OSError:
                continue
        if self.lib is None:
            raise CudaUnavailable("CUDA driver library not available")
        self._bind()
        self._check(self.cuInit(0), "cuInit")

    def _function(self, *names: str):
        for name in names:
            fn = getattr(self.lib, name, None)
            if fn is not None:
                return fn
        raise CudaUnavailable(f"CUDA driver symbol unavailable: {names[0]}")

    def _bind(self) -> None:
        self.cuInit = self._function("cuInit")
        self.cuDeviceGetCount = self._function("cuDeviceGetCount")
        self.cuDeviceGet = self._function("cuDeviceGet")
        self.cuDeviceGetName = self._function("cuDeviceGetName")
        self.cuDeviceTotalMem = self._function("cuDeviceTotalMem_v2", "cuDeviceTotalMem")
        self.cuDeviceGetUuid = getattr(self.lib, "cuDeviceGetUuid_v2", None) or getattr(self.lib, "cuDeviceGetUuid", None)
        self.cuCtxCreate = self._function("cuCtxCreate_v2", "cuCtxCreate")
        self.cuCtxDestroy = self._function("cuCtxDestroy_v2", "cuCtxDestroy")
        self.cuMemAlloc = self._function("cuMemAlloc_v2", "cuMemAlloc")
        self.cuMemFree = self._function("cuMemFree_v2", "cuMemFree")
        self.cuMemHostAlloc = self._function("cuMemHostAlloc")
        self.cuMemFreeHost = self._function("cuMemFreeHost")
        self.cuMemcpyHtoD = self._function("cuMemcpyHtoD_v2", "cuMemcpyHtoD")
        self.cuMemcpyDtoH = self._function("cuMemcpyDtoH_v2", "cuMemcpyDtoH")
        self.cuMemcpyDtoD = self._function("cuMemcpyDtoD_v2", "cuMemcpyDtoD")
        self.cuEventCreate = self._function("cuEventCreate")
        self.cuEventRecord = self._function("cuEventRecord")
        self.cuEventSynchronize = self._function("cuEventSynchronize")
        self.cuEventElapsedTime = self._function("cuEventElapsedTime")
        self.cuEventDestroy = self._function("cuEventDestroy_v2", "cuEventDestroy")
        self.cuModuleLoadData = self._function("cuModuleLoadData")
        self.cuModuleUnload = self._function("cuModuleUnload")
        self.cuModuleGetFunction = self._function("cuModuleGetFunction")
        self.cuLaunchKernel = self._function("cuLaunchKernel")
        self.cuCtxSynchronize = self._function("cuCtxSynchronize")

    @staticmethod
    def _check(code: int, operation: str) -> None:
        if int(code) != 0:
            raise CudaUnavailable(f"{operation} failed with CUDA error {int(code)}")

    def device_count(self) -> int:
        count = ctypes.c_int()
        self._check(self.cuDeviceGetCount(ctypes.byref(count)), "cuDeviceGetCount")
        return count.value

    def device(self, index: int) -> int:
        device = ctypes.c_int()
        self._check(self.cuDeviceGet(ctypes.byref(device), index), "cuDeviceGet")
        return device.value

    def identity(self, index: int) -> CudaDeviceIdentity:
        device = self.device(index)
        name = ctypes.create_string_buffer(256)
        self._check(self.cuDeviceGetName(name, len(name), device), "cuDeviceGetName")
        total = ctypes.c_size_t()
        self._check(self.cuDeviceTotalMem(ctypes.byref(total), device), "cuDeviceTotalMem")
        uuid_text = None
        if self.cuDeviceGetUuid is not None:
            uuid_bytes = (ctypes.c_ubyte * 16)()
            if int(self.cuDeviceGetUuid(ctypes.byref(uuid_bytes), device)) == 0:
                raw = bytes(uuid_bytes)
                uuid_text = raw.hex()
        return CudaDeviceIdentity(index, name.value.decode("utf-8", errors="replace"), uuid_text, total.value)

    def context(self, index: int) -> ctypes.c_void_p:
        ctx = ctypes.c_void_p()
        self._check(self.cuCtxCreate(ctypes.byref(ctx), 0, self.device(index)), "cuCtxCreate")
        return ctx

    def timed(self, operation, repeats: int = 1) -> list[float]:
        samples: list[float] = []
        for _ in range(repeats):
            start = ctypes.c_void_p()
            end = ctypes.c_void_p()
            self._check(self.cuEventCreate(ctypes.byref(start), 0), "cuEventCreate")
            self._check(self.cuEventCreate(ctypes.byref(end), 0), "cuEventCreate")
            try:
                self._check(self.cuEventRecord(start, 0), "cuEventRecord")
                operation()
                self._check(self.cuEventRecord(end, 0), "cuEventRecord")
                self._check(self.cuEventSynchronize(end), "cuEventSynchronize")
                elapsed = ctypes.c_float()
                self._check(self.cuEventElapsedTime(ctypes.byref(elapsed), start, end), "cuEventElapsedTime")
                samples.append(float(elapsed.value) / 1000.0)
            finally:
                self.cuEventDestroy(start)
                self.cuEventDestroy(end)
        return samples


def _throughput(samples: list[float], bytes_per_sample: int) -> dict[str, object]:
    median = statistics.median(samples)
    rate = bytes_per_sample / median if median > 0 else 0.0
    return {
        "sample_count": len(samples),
        "sample_seconds": samples,
        "median_seconds": median,
        "bytes_per_sample": bytes_per_sample,
        "throughput_bytes_per_second": rate,
        "throughput_gib_per_second": rate / (1024 ** 3),
    }


def transfer_benchmarks(driver: CudaDriver, index: int, *, buffer_bytes: int = 64 * 1024 * 1024, repeats_per_sample: int = 8, sample_count: int = 5) -> list[dict[str, Any]]:
    identity = driver.identity(index)
    target = identity.target()
    ctx = driver.context(index)
    src = ctypes.c_uint64()
    dst = ctypes.c_uint64()
    host = ctypes.c_void_p()
    try:
        driver._check(driver.cuMemAlloc(ctypes.byref(src), buffer_bytes), "cuMemAlloc")
        driver._check(driver.cuMemAlloc(ctypes.byref(dst), buffer_bytes), "cuMemAlloc")
        driver._check(driver.cuMemHostAlloc(ctypes.byref(host), buffer_bytes, 0), "cuMemHostAlloc")
        ctypes.memset(host, 0xA5, buffer_bytes)
        driver._check(driver.cuMemcpyHtoD(src.value, host, buffer_bytes), "cuMemcpyHtoD")

        def d2d() -> None:
            for _ in range(repeats_per_sample):
                driver._check(driver.cuMemcpyDtoD(dst.value, src.value, buffer_bytes), "cuMemcpyDtoD")

        def h2d() -> None:
            for _ in range(repeats_per_sample):
                driver._check(driver.cuMemcpyHtoD(dst.value, host, buffer_bytes), "cuMemcpyHtoD")

        def d2h() -> None:
            for _ in range(repeats_per_sample):
                driver._check(driver.cuMemcpyDtoH(host, src.value, buffer_bytes), "cuMemcpyDtoH")

        tests = []
        for benchmark_id, label, method, op in (
            ("lmts.reference.gpu.d2d", "Device to device copy", "cuda_memcpy_d2d", d2d),
            ("lmts.reference.gpu.h2d_pinned", "Pinned host to device copy", "cuda_memcpy_h2d", h2d),
            ("lmts.reference.gpu.d2h_pinned", "Device to pinned host copy", "cuda_memcpy_d2h", d2h),
        ):
            op()
            samples = driver.timed(op, sample_count)
            tests.append({
                "benchmark_id": benchmark_id,
                "label": label,
                "method": method,
                "method_version": 1,
                "status": "completed",
                "target": target,
                "metrics": {
                    **_throughput(samples, buffer_bytes * repeats_per_sample),
                    "buffer_bytes": buffer_bytes,
                    "repeats_per_sample": repeats_per_sample,
                    "host_memory": "pinned" if "pinned" in benchmark_id else None,
                },
            })
        return tests
    finally:
        if host.value:
            driver.cuMemFreeHost(host)
        if dst.value:
            driver.cuMemFree(dst.value)
        if src.value:
            driver.cuMemFree(src.value)
        driver.cuCtxDestroy(ctx)


_PTX = r'''
.version 6.0
.target sm_52
.address_size 64

.visible .entry lmts_fma(
    .param .u64 data,
    .param .u32 iterations
)
{
    .reg .pred %p;
    .reg .b32 %r<5>;
    .reg .b64 %rd<5>;
    .reg .f32 %f<4>;

    ld.param.u64 %rd1, [data];
    ld.param.u32 %r1, [iterations];
    mov.u32 %r2, %tid.x;
    mov.u32 %r3, %ctaid.x;
    mov.u32 %r4, %ntid.x;
    mad.lo.s32 %r2, %r3, %r4, %r2;
    mul.wide.u32 %rd2, %r2, 4;
    add.s64 %rd3, %rd1, %rd2;
    ld.global.f32 %f1, [%rd3];
    mov.f32 %f2, 1.000001;
    mov.f32 %f3, 0.000001;
    mov.u32 %r2, 0;
LOOP:
    fma.rn.f32 %f1, %f1, %f2, %f3;
    add.u32 %r2, %r2, 1;
    setp.lt.u32 %p, %r2, %r1;
    @%p bra LOOP;
    st.global.f32 [%rd3], %f1;
    ret;
}
'''


def compute_benchmark(driver: CudaDriver, index: int, *, blocks: int = 4096, threads: int = 256, iterations: int = 4096, sample_count: int = 5) -> dict[str, Any]:
    identity = driver.identity(index)
    ctx = driver.context(index)
    data = ctypes.c_uint64()
    module = ctypes.c_void_p()
    function = ctypes.c_void_p()
    element_count = blocks * threads
    size = element_count * 4
    try:
        driver._check(driver.cuMemAlloc(ctypes.byref(data), size), "cuMemAlloc")
        ptx = ctypes.create_string_buffer(_PTX.encode("ascii"))
        driver._check(driver.cuModuleLoadData(ctypes.byref(module), ctypes.cast(ptx, ctypes.c_void_p)), "cuModuleLoadData")
        driver._check(driver.cuModuleGetFunction(ctypes.byref(function), module, b"lmts_fma"), "cuModuleGetFunction")
        iterations_arg = ctypes.c_uint(iterations)
        data_arg = ctypes.c_uint64(data.value)
        args = (ctypes.c_void_p * 2)(ctypes.cast(ctypes.byref(data_arg), ctypes.c_void_p), ctypes.cast(ctypes.byref(iterations_arg), ctypes.c_void_p))

        def launch() -> None:
            driver._check(driver.cuLaunchKernel(function, blocks, 1, 1, threads, 1, 1, 0, 0, args, None), "cuLaunchKernel")

        launch()
        driver._check(driver.cuCtxSynchronize(), "cuCtxSynchronize")
        samples = driver.timed(launch, sample_count)
        median = statistics.median(samples)
        operations = element_count * iterations * 2
        return {
            "benchmark_id": "lmts.reference.gpu.fma_fp32",
            "label": "FP32 FMA kernel",
            "method": "cuda_ptx_fma_fp32",
            "method_version": 1,
            "status": "completed",
            "target": identity.target(),
            "metrics": {
                "sample_count": len(samples),
                "sample_seconds": samples,
                "median_seconds": median,
                "blocks": blocks,
                "threads_per_block": threads,
                "iterations_per_thread": iterations,
                "operations_per_sample": operations,
                "operations_per_second": operations / median if median > 0 else 0.0,
                "gigaoperations_per_second": operations / median / 1_000_000_000 if median > 0 else 0.0,
            },
        }
    finally:
        if module.value:
            driver.cuModuleUnload(module)
        if data.value:
            driver.cuMemFree(data.value)
        driver.cuCtxDestroy(ctx)


def run_cuda_reference() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    driver = CudaDriver()
    count = driver.device_count()
    if count < 1:
        raise CudaUnavailable("CUDA driver reports no devices")
    tests: list[dict[str, Any]] = []
    devices: list[dict[str, Any]] = []
    for index in range(count):
        identity = driver.identity(index)
        devices.append({
            **identity.target(),
            "total_memory_bytes": identity.total_memory_bytes,
        })
        tests.extend(transfer_benchmarks(driver, index))
        tests.append(compute_benchmark(driver, index))
    return tests, {"devices": devices, "backend": "cuda_driver_api"}
