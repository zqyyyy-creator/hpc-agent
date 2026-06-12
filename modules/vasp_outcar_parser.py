"""Deterministic VASP OUTCAR / OSZICAR parser.

Extracts structured facts from VASP output files so the LLM report
generator receives authoritative numeric data instead of having to
"read" energy values from free-form log snippets.
"""

import re
from pathlib import Path


def _find_block(text: str, start_marker: str, end_marker: str | None = None) -> str | None:
    """Return text between start_marker and end_marker (or EOF)."""
    idx = text.find(start_marker)
    if idx == -1:
        return None
    chunk = text[idx + len(start_marker):]
    if end_marker is not None:
        end_idx = chunk.find(end_marker)
        if end_idx != -1:
            chunk = chunk[:end_idx]
    return chunk


def _read_tail_limited(path: Path, max_chars: int = 4000) -> str:
    if not path.is_file():
        return ""
    size = path.stat().st_size
    with path.open("rb") as f:
        if size > max_chars:
            f.seek(max(0, size - max_chars))
        data = f.read(max_chars)
    return data.decode("utf-8", errors="replace")


def _read_full(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# OUTCAR parsers
# ---------------------------------------------------------------------------

def _parse_convergence(outcar: str) -> dict:
    """Determine whether the SCF loop converged."""
    reached = "reached required accuracy" in outcar
    ediff_abort = "aborting loop because EDIFF is reached" in outcar
    error_signals = [
        ("forrtl: severe", "Fortran runtime error"),
        ("SIGSEGV", "Segmentation fault"),
        ("oom-kill", "Out of memory"),
        ("traceback", "Python traceback"),
    ]
    errors = [msg for keyword, msg in error_signals if keyword.lower() in outcar.lower()]

    # Count DAV/RMM iterations from LOOP+ line
    loop_match = re.search(r"LOOP\+:\s+cpu time\s+([\d.]+)", outcar)
    loop_cpu = float(loop_match.group(1)) if loop_match else None

    return {
        "converged": reached or ediff_abort,
        "converged_reason": (
            "reached required accuracy" if reached
            else "aborting loop because EDIFF is reached" if ediff_abort
            else "not converged"
        ),
        "errors": errors,
        "loop_cpu_time": loop_cpu,
    }


def _parse_free_energy(outcar: str) -> dict:
    """Extract the FREE ENERGIE block."""
    block = _find_block(outcar, "FREE ENERGIE OF THE ION-ELECTRON SYSTEM (eV)")
    if block is None:
        return {}

    result = {}
    for line in block.splitlines():
        line = line.strip()
        m = re.search(r"free\s+energy\s+TOTEN\s*=\s*([\dE.+-]+)", line, re.IGNORECASE)
        if m:
            result["toten"] = float(m.group(1).replace("E", "e").replace("+", "+").replace("-", "-").replace("+-", "e-").replace("D", "e"))
        m = re.search(r"energy\s+without entropy\s*=\s*([\dE.+-]+)", line, re.IGNORECASE)
        if m:
            result["energy_without_entropy"] = float(m.group(1).replace("E", "e").replace("D", "e"))
        m = re.search(r"energy\(sigma->0\)\s*=\s*([\dE.+-]+)", line, re.IGNORECASE)
        if m:
            result["energy_sigma0"] = float(m.group(1).replace("E", "e").replace("D", "e"))

    # Also match the compact form: "free  energy   TOTEN  =        -3.45441312 eV"
    if "toten" not in result:
        m = re.search(
            r"free\s+energy\s+TOTEN\s*=\s*([\d.+-]+)\s*eV",
            outcar[outcar.find("FREE ENERGIE"):] if "FREE ENERGIE" in outcar else "",
            re.IGNORECASE,
        )
        if m:
            try:
                result["toten"] = float(m.group(1))
            except ValueError:
                pass

    return result


def _parse_efermi(outcar: str) -> dict:
    """Extract E-fermi."""
    m = re.search(r"E-fermi\s*:\s*([\d.+-]+)", outcar)
    result = {}
    if m:
        result["efermi"] = float(m.group(1))

    # ISMEAR / SIGMA
    sm = re.search(r"ISMEAR\s*=\s*(\d+);\s*SIGMA\s*=\s*([\d.]+)", outcar)
    if sm:
        result["ismear"] = int(sm.group(1))
        result["sigma"] = float(sm.group(2))

    # NELECT
    nm = re.search(r"NELECT\s*=\s*([\d.]+)\s+total number of electrons", outcar)
    if nm:
        result["nelect"] = float(nm.group(1))

    return result


def _parse_volume(outcar: str) -> dict:
    """Extract cell volume."""
    block = _find_block(outcar, "VOLUME and BASIS-vectors are now :")
    if block is None:
        return {}

    m = re.search(r"volume of cell\s*:\s*([\d.]+)", block)
    result = {}
    if m:
        result["volume"] = float(m.group(1))

    m = re.search(r"energy-cutoff\s*:\s*([\d.]+)", block)
    if m:
        result["encut_used"] = float(m.group(1))

    # lattice vectors
    lattice = re.findall(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", block)
    if len(lattice) >= 3:
        result["lattice_vectors"] = [
            [float(v) for v in lattice[i][:3]] for i in range(3)
        ]

    return result


def _parse_stress(outcar: str) -> dict:
    """Extract stress tensor."""
    m = re.search(r"in kB\s+([\d.+-]+)\s+([\d.+-]+)\s+([\d.+-]+)\s+([\d.+-]+)\s+([\d.+-]+)\s+([\d.+-]+)", outcar)
    result = {}
    if m:
        result["stress_kB"] = [float(m.group(i)) for i in range(1, 7)]

    m = re.search(r"external pressure\s*=\s*([\d.+-]+)\s*kB", outcar)
    if m:
        result["external_pressure_kB"] = float(m.group(1))

    return result


def _parse_forces(outcar: str) -> dict:
    """Extract total forces on ions."""
    block = _find_block(outcar, "POSITION                                       TOTAL-FORCE (eV/Angst)")
    if block is None:
        return {}

    forces = []
    for line in block.splitlines():
        parts = line.strip().split()
        if len(parts) == 7:
            try:
                forces.append([float(p) for p in parts[4:]])
            except ValueError:
                continue
        elif len(parts) == 4:
            try:
                forces.append([float(p) for p in parts[1:]])
            except ValueError:
                continue

    if not forces:
        return {}

    max_force = max(max(abs(f[0]), abs(f[1]), abs(f[2])) for f in forces)
    force_norms = [(f[0]**2 + f[1]**2 + f[2]**2)**0.5 for f in forces]
    mean_force_norm = sum(force_norms) / len(force_norms)

    return {
        "num_ions": len(forces),
        "max_force_eV_A": round(max_force, 6),
        "mean_force_norm_eV_A": round(mean_force_norm, 6),
        "drift": None,  # parsed separately
    }


def _parse_timing(outcar: str) -> dict:
    """Extract timing and memory."""
    result = {}
    m = re.search(r"Total CPU time used \(sec\):\s*([\d.]+)", outcar)
    if m:
        result["total_cpu_time_sec"] = float(m.group(1))
    m = re.search(r"Elapsed time \(sec\):\s*([\d.]+)", outcar)
    if m:
        result["elapsed_time_sec"] = float(m.group(1))
    m = re.search(r"Maximum memory used \(kb\):\s*([\d.]+)", outcar)
    if m:
        result["max_memory_kb"] = float(m.group(1))

    return result


def _parse_band_info(outcar: str) -> dict:
    """Extract band energies around Fermi level."""
    block = _find_block(outcar, "E-fermi :")
    if block is None:
        return {}

    # Find the k-point block
    kp_idx = block.find("k-point")
    if kp_idx == -1:
        return {}
    lines = block[kp_idx:].splitlines()

    bands = []
    for line in lines[1:]:
        parts = line.strip().split()
        if len(parts) < 3:
            break
        try:
            band_no = int(parts[0])
            energy = float(parts[1])
            occ = float(parts[2])
            bands.append({"band": band_no, "energy": energy, "occupation": occ})
        except ValueError:
            break

    if not bands:
        return {}

    occupied = [b for b in bands if b["occupation"] > 0.5]
    unoccupied = [b for b in bands if b["occupation"] <= 0.5]
    vbm = max(b["energy"] for b in occupied) if occupied else None
    cbm = min(b["energy"] for b in unoccupied) if unoccupied else None
    gap = round(cbm - vbm, 6) if vbm is not None and cbm is not None else None

    return {
        "num_bands": len(bands),
        "vbm_eV": vbm,
        "cbm_eV": cbm,
        "band_gap_eV": gap,
    }


def _parse_ion_info(outcar: str) -> dict:
    """Extract ion types and counts."""
    m = re.search(r"POSCAR found type information on POSCAR\s+(.*)", outcar)
    result = {}
    ion_types = []
    if m:
        ion_types = m.group(1).strip().split()

    m = re.search(r"POSCAR found\s*:\s*(\d+)\s+types and\s+(\d+)\s+ions", outcar)
    if m:
        result["num_types"] = int(m.group(1))
        result["num_ions"] = int(m.group(2))

    if ion_types:
        result["species"] = ion_types

    # POMASS / ZVAL
    pomass = re.findall(r"POMASS\s*=\s*([\d.]+)", outcar)
    zval = re.findall(r"ZVAL\s*=\s*([\d.]+)", outcar)
    if pomass:
        result["atomic_masses"] = [float(m) for m in pomass]
    if zval:
        result["zval"] = [float(z) for z in zval]

    # NATOM
    m = re.search(r"NIONS\s*=\s*(\d+)", outcar)
    if m:
        result["nions"] = int(m.group(1))

    return result


# ---------------------------------------------------------------------------
# OSZICAR parsers
# ---------------------------------------------------------------------------

def _parse_oszicar(oszicar_text: str) -> dict:
    """Parse OSZICAR for iteration count and convergence path."""
    if not oszicar_text.strip():
        return {}

    lines = oszicar_text.splitlines()
    iterations = 0
    final_f = None
    final_e0 = None
    final_de = None
    energy_path = []

    for line in lines:
        # Count DAV/RMM iterations
        if re.match(r"(DAV|RMM):\s+\d+", line.strip()):
            iterations += 1
            parts = line.strip().split()
            if len(parts) >= 3:
                try:
                    energy = float(parts[2])
                    energy_path.append(energy)
                except ValueError:
                    pass

        # Match final line: "   1 F= -.34544131E+01 E0= -.34510716E+01  d E =-.668308E-02"
        m = re.match(r"\s*\d+\s+F=\s*([\dE.+-]+)\s+E0=\s*([\dE.+-]+)\s+d\s*E\s*=\s*([\dE.+-]+)", line)
        if m:
            try:
                final_f = float(m.group(1).replace("E", "e").replace("D", "e"))
            except ValueError:
                pass
            try:
                final_e0 = float(m.group(2).replace("E", "e").replace("D", "e"))
            except ValueError:
                pass
            try:
                final_de = float(m.group(3).replace("E", "e").replace("D", "e"))
            except ValueError:
                pass

    result = {"iterations": iterations}
    if final_f is not None:
        result["F"] = final_f
    if final_e0 is not None:
        result["E0"] = final_e0
    if final_de is not None:
        result["dE"] = final_de

    # Energy range for judging convergence quality
    if energy_path:
        result["energy_range_eV"] = round(max(energy_path) - min(energy_path), 4)
        result["energy_path_length"] = len(energy_path)

    return result


# ---------------------------------------------------------------------------
# Top-level parser
# ---------------------------------------------------------------------------

def parse_vasp_results(raw_output_dir: Path) -> dict:
    """Parse all deterministic facts from OUTCAR and OSZICAR.

    Returns a dict with sections: convergence, energy, electronic, cell,
    stress, forces, timing, band_structure, ions, oszicar.
    """
    outcar_path = raw_output_dir / "OUTCAR"
    oszicar_path = raw_output_dir / "OSZICAR"

    if not outcar_path.is_file():
        return {"error": "OUTCAR not found"}

    outcar = _read_full(outcar_path)
    oszicar = _read_full(oszicar_path)

    facts = {
        "convergence": _parse_convergence(outcar),
        "energy": _parse_free_energy(outcar),
        "electronic": _parse_efermi(outcar),
        "cell": _parse_volume(outcar),
        "stress": _parse_stress(outcar),
        "forces": _parse_forces(outcar),
        "timing": _parse_timing(outcar),
        "band_structure": _parse_band_info(outcar),
        "ions": _parse_ion_info(outcar),
        "oszicar": _parse_oszicar(oszicar),
    }

    return facts


# ---------------------------------------------------------------------------
# Formatter: produces the "VASP Facts" Markdown block for report_context.md
# ---------------------------------------------------------------------------

def format_facts_block(facts: dict) -> str:
    """Render parsed VASP facts as a deterministic Markdown block.

    The LLM is instructed to treat this block as the sole authoritative
    source for numeric results.
    """

    def l(key: str) -> str:
        """Look up a dotted path like 'energy.toten' in facts dict."""
        parts = key.split(".")
        val = facts
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            else:
                val = None
        return val

    def has(key: str) -> bool:
        return l(key) is not None

    lines = [
        "# VASP Deterministic Facts",
        "",
        "> The values below are parsed deterministically from OUTCAR / OSZICAR.",
        "> They are the **single authoritative source** for numerical results.",
        "> Do not extract energies, forces, or convergence status from log snippets.",
        "",
    ]

    # -- Convergence --
    if has("convergence"):
        c = l("convergence")
        lines.append("## Convergence")
        lines.append(f"- Converged: **{c['converged']}**")
        lines.append(f"- Reason: {c['converged_reason']}")
        if c.get("errors"):
            lines.append(f"- Errors detected: {', '.join(c['errors'])}")
        lines.append("")

    # -- Energy --
    if has("energy.toten"):
        e = l("energy")
        lines.append("## Energies")
        lines.append(f"- TOTEN (free energy) = **{e['toten']:.8f}** eV")
        if "energy_without_entropy" in e:
            lines.append(f"- Energy without entropy = **{e['energy_without_entropy']:.8f}** eV")
        if "energy_sigma0" in e:
            lines.append(f"- Energy (sigma→0) = **{e['energy_sigma0']:.8f}** eV")
        lines.append("")

    # -- OSZICAR --
    if has("oszicar.iterations"):
        o = l("oszicar")
        lines.append("## SCF Convergence Path (OSZICAR)")
        lines.append(f"- Electronic iterations: **{o['iterations']}**")
        if "F" in o:
            lines.append(f"- Final F = **{o['F']:.8f}** eV")
        if "E0" in o:
            lines.append(f"- Final E0 = **{o['E0']:.8f}** eV")
        if "dE" in o:
            lines.append(f"- dE = **{o['dE']:.8f}** eV")
        if "energy_range_eV" in o:
            lines.append(f"- Energy range across all iterations: **{o['energy_range_eV']:.4f}** eV")
        lines.append("")

    # -- Electronic --
    if has("electronic.efermi"):
        el = l("electronic")
        lines.append("## Electronic Structure")
        lines.append(f"- E-fermi = **{el['efermi']:.4f}** eV")
        if "ismear" in el:
            lines.append(f"- ISMEAR = {el['ismear']}")
        if "sigma" in el:
            lines.append(f"- SIGMA = {el['sigma']}")
        if "nelect" in el:
            lines.append(f"- NELECT = {el['nelect']}")
        lines.append("")

    # -- Band Structure --
    if has("band_structure.vbm_eV"):
        bs = l("band_structure")
        lines.append("## Band Structure (Gamma point)")
        lines.append(f"- VBM = **{bs['vbm_eV']:.4f}** eV")
        lines.append(f"- CBM = **{bs['cbm_eV']:.4f}** eV")
        lines.append(f"- Band gap = **{bs['band_gap_eV']:.4f}** eV")
        lines.append("")

    # -- Cell --
    if has("cell.volume"):
        ce = l("cell")
        lines.append("## Cell")
        lines.append(f"- Volume = **{ce['volume']:.4f}** Å³")
        if "encut_used" in ce:
            lines.append(f"- ENCUT used = {ce['encut_used']:.2f} eV")
        lines.append("")

    # -- Stress --
    if has("stress.stress_kB"):
        s = l("stress")
        stress = s["stress_kB"]
        lines.append("## Stress Tensor (kB)")
        lines.append(f"- XX = {stress[0]:.2f}, YY = {stress[1]:.2f}, ZZ = {stress[2]:.2f}")
        lines.append(f"- XY = {stress[3]:.2f}, YZ = {stress[4]:.2f}, ZX = {stress[5]:.2f}")
        if "external_pressure_kB" in s:
            lines.append(f"- External pressure = **{s['external_pressure_kB']:.2f}** kB")
        lines.append("")

    # -- Forces --
    if has("forces.max_force_eV_A"):
        f = l("forces")
        lines.append("## Forces")
        lines.append(f"- Number of ions: {f['num_ions']}")
        lines.append(f"- Max |force| = **{f['max_force_eV_A']:.6f}** eV/Å")
        lines.append(f"- Mean force norm = **{f['mean_force_norm_eV_A']:.6f}** eV/Å")
        lines.append("")

    # -- Ions --
    if has("ions.species"):
        io = l("ions")
        lines.append("## Ions")
        if io.get("species"):
            lines.append(f"- Species: {', '.join(io['species'])}")
        if io.get("num_ions"):
            lines.append(f"- Total atoms: {io['num_ions']}")
        if io.get("nions"):
            lines.append(f"- NIONS: {io['nions']}")
        lines.append("")

    # -- Timing --
    if has("timing.total_cpu_time_sec"):
        t = l("timing")
        lines.append("## Performance")
        lines.append(f"- Total CPU time: {t['total_cpu_time_sec']:.2f} s")
        if "elapsed_time_sec" in t:
            lines.append(f"- Elapsed time: {t['elapsed_time_sec']:.2f} s")
        if "max_memory_kb" in t:
            lines.append(f"- Max memory: {t['max_memory_kb']:.0f} kB")
        lines.append("")

    return "\n".join(lines)