"""
ConnectomeArena Continuous Rate ODE Simulation Backend (Grant 1FAB0).

Provides continuous rate dynamics over the Drosophila connectome graph G_traced:
    tau_i * dr_i/dt = -r_i + phi(sum_j W_ij * r_j + I_i^stim)

Features:
  - Vectorized continuous rate dynamics with Euler numerical integration.
  - Sigmoidal activation: phi(x) = r_max / (1 + exp(-k * (x - x_0)))
  - Rectified linear activation: phi(x) = clip(k * (x - x_0), 0, r_max)
  - Two null controls:
      * Degree-preserving shuffled twin (permuted postsynaptic targets).
      * Sign-preserving random dynamics twin (permuted signs, randomized time constants and parameters).
  - Null Twin Stream Offsets: Shuffled twin uses seed 1000 + seed (permuting postsynaptic endpoints).
    Random twin uses seed 2000 + seed (randomized time constants and activation parameters) and
    seed 3000 + seed (permuted signs), sharing random stream offsets with the LIF spiking path.
  - Named class interface:
      * Driving named input classes (e.g. ORN_DM1, LC4, T4/T5, female_taste).
      * Collecting per-step firing rates on named readout classes (DNp09, MDN, DNa02_L/R, DNp01, pC1, pIP10).
  - Seamless integration with continuous 2D trajectory decoding (src/trajectory.py).
"""

from __future__ import annotations
import math
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union, Any
import numpy as np

try:
    from src.trajectory import integrate_trajectory, trajectory_metrics, Trajectory
except ImportError:
    from trajectory import integrate_trajectory, trajectory_metrics, Trajectory


class ConnectomeArenaSimulation:
    """
    Continuous neural rate ODE simulation engine over connectome graphs.

    Parameters
    ----------
    weights : sparse matrix, COO tuple (row, col, data), or 2D array
        Directed synaptic connectivity where W_ij is the edge from pre j to post i.
    signs : np.ndarray, optional
        Presynaptic sign vector (-1 for inhibitory, +1 for excitatory).
    num_neurons : int, optional
        Total number of neurons in the circuit. Inferred from weights/annotations if omitted.
    neuron_types : sequence of str, optional
        Cell type annotations for each neuron index.
    soma_sides : sequence of str, optional
        Soma side annotations ('L', 'R', or '') for each neuron index.
    receptor_types : sequence of str, optional
        Receptor type annotations for each neuron index.
    body_ids : sequence of int, optional
        Body IDs for each neuron index.
    class_map : dict, optional
        Explicit mapping from class names to neuron indices: {name: [idx, ...]}.
    tau_ms : float or np.ndarray, default 20.0
        Membrane/rate time constant in milliseconds (Shiu et al. reference: 20 ms).
    r_max : float, default 150.0
        Maximum saturation firing rate in Hz.
    gain_k : float, default 0.1
        Gain/slope parameter of the activation function.
    x0 : float or np.ndarray, default 0.0
        Midpoint / activation threshold offset.
    activation : str, default 'sigmoid'
        Activation function: 'sigmoid' or 'relu'.
    dt_ms : float, default 1.0
        Euler integration timestep in milliseconds.
    w_scale : float, default 1.0
        Global synaptic weight scaling factor.
    condition : str, default 'real'
        Model condition: 'real', 'shuffled' (degree-preserving rewire),
        or 'random' (random dynamics twin).
    seed : int, optional
        Random seed for reproducible twin generation and jitter.
    r_baseline : float, default 0.0
        Initial resting firing rate (Hz) for all neurons.

    Null Twin Stream Offsets:
    - Shuffled twin: uses seed 1000 + seed (permuting postsynaptic endpoints).
    - Random twin: uses seed 2000 + seed (randomized time constants and activation parameters)
      and seed 3000 + seed (permuted signs), sharing random stream offsets with the LIF spiking path.
    """

    def __init__(
        self,
        weights: Any = None,
        signs: Optional[np.ndarray] = None,
        num_neurons: Optional[int] = None,
        neuron_types: Optional[Sequence[str]] = None,
        soma_sides: Optional[Sequence[str]] = None,
        receptor_types: Optional[Sequence[str]] = None,
        body_ids: Optional[Sequence[int]] = None,
        class_map: Optional[Dict[str, Sequence[int]]] = None,
        tau_ms: Union[float, np.ndarray] = 20.0,
        r_max: float = 150.0,
        gain_k: float = 0.1,
        x0: Union[float, np.ndarray] = 0.0,
        activation: str = "sigmoid",
        dt_ms: float = 1.0,
        w_scale: float = 1.0,
        condition: str = "real",
        seed: Optional[int] = None,
        r_baseline: float = 0.0,
    ) -> None:
        self.condition = condition.lower()
        self.seed = seed
        self.activation_type = activation.lower()
        self.r_max = float(r_max)
        self.gain_k = float(gain_k)
        self.dt_ms = float(dt_ms)
        self.w_scale = float(w_scale)
        self.r_baseline = float(r_baseline)

        # Parse annotations
        self.neuron_types = np.array(neuron_types) if neuron_types is not None else None
        self.soma_sides = np.array(soma_sides) if soma_sides is not None else None
        self.receptor_types = np.array(receptor_types) if receptor_types is not None else None
        self.body_ids = np.array(body_ids) if body_ids is not None else None
        self.class_map = {k: np.array(v, dtype=int) for k, v in class_map.items()} if class_map else {}

        # Determine neuron count n
        n = num_neurons
        if n is None:
            if self.neuron_types is not None:
                n = len(self.neuron_types)
            elif self.body_ids is not None:
                n = len(self.body_ids)
            elif weights is not None:
                if hasattr(weights, "shape"):
                    n = weights.shape[0]
                elif isinstance(weights, tuple) and len(weights) == 3:
                    n = max(int(np.max(weights[0])), int(np.max(weights[1]))) + 1
            else:
                n = 0
        self.n = int(n)

        # Ingest weights into COO representation (row, col, data)
        self.signs = np.asarray(signs, dtype=np.float32) if signs is not None else None
        self._init_weights(weights)

        # Initialize rate parameters (tau, x0, jitter)
        self._init_parameters(tau_ms, x0)

        # State vector: instantaneous rates in Hz
        self.r = np.full(self.n, self.r_baseline, dtype=np.float64)

    def _init_weights(self, weights: Any) -> None:
        """Parses and formats weights into internal sparse COO arrays."""
        if weights is None:
            self.row = np.empty(0, dtype=np.int64)
            self.col = np.empty(0, dtype=np.int64)
            self.data = np.empty(0, dtype=np.float32)
            return

        # Scipy sparse or object with row, col, data
        if hasattr(weights, "tocoo"):
            coo = weights.tocoo()
            row, col, data = coo.row, coo.col, coo.data
        elif isinstance(weights, tuple) and len(weights) == 3:
            row, col, data = weights
        elif hasattr(weights, "row") and hasattr(weights, "col") and hasattr(weights, "data"):
            row, col, data = weights.row, weights.col, weights.data
        elif isinstance(weights, np.ndarray) and weights.ndim == 2:
            nonzero_idx = np.nonzero(weights)
            row = nonzero_idx[0]
            col = nonzero_idx[1]
            data = weights[nonzero_idx]
        else:
            raise TypeError(f"Unsupported weight matrix representation: {type(weights)}")

        self.row = np.asarray(row, dtype=np.int64)
        self.col = np.asarray(col, dtype=np.int64)
        self.data = np.asarray(data, dtype=np.float32)

        # Apply presynaptic sign if provided and data is strictly positive
        if self.signs is not None and len(self.signs) == self.n:
            if np.all(self.data >= 0):
                self.data = self.data * self.signs[self.col]

        # Apply null model transformations if requested
        if self.condition == "shuffled":
            # Degree-preserving rewire: permute postsynaptic endpoints (rows)
            # Preserves in-degree and out-degree of every node, and preserves presynaptic signs
            rng = np.random.default_rng(1000 + (self.seed if self.seed is not None else 0))
            perm = rng.permutation(len(self.row))
            self.row = self.row[perm]

        elif self.condition == "random":
            # Sign-permuted twin: permutes presynaptic signs across neurons
            rng = np.random.default_rng(3000 + (self.seed if self.seed is not None else 0))
            if self.signs is not None and len(self.signs) == self.n:
                perm_signs = self.signs[rng.permutation(self.n)]
                self.data = np.abs(self.data) * perm_signs[self.col]
            else:
                s = np.sign(self.data)
                s = s[rng.permutation(len(s))]
                self.data = np.abs(self.data) * s

    def _init_parameters(self, tau_ms: Union[float, np.ndarray], x0: Union[float, np.ndarray]) -> None:
        """Initializes ODE parameters, applying randomized parameters for the random null twin."""
        if self.condition == "random":
            rng = np.random.default_rng(2000 + (self.seed if self.seed is not None else 0))
            # Randomized membrane time constant drawn U[5, 80] ms
            base_tau = rng.uniform(5.0, 80.0)
            self.tau = np.full(self.n, base_tau, dtype=np.float64)
            # Per-neuron log-uniform jitter in [0.5, 2.0]
            self.jitter = np.exp(rng.uniform(np.log(0.5), np.log(2.0), size=self.n))
            # Random weight scale in logU[0.05, 1.5]
            self.w_scale = float(np.exp(rng.uniform(np.log(0.05), np.log(1.5))))
            # Random activation threshold drawn U[3, 20]
            self.x0 = np.full(self.n, rng.uniform(3.0, 20.0), dtype=np.float64)
        else:
            if isinstance(tau_ms, (int, float)):
                self.tau = np.full(self.n, float(tau_ms), dtype=np.float64)
            else:
                self.tau = np.asarray(tau_ms, dtype=np.float64)

            if isinstance(x0, (int, float)):
                self.x0 = np.full(self.n, float(x0), dtype=np.float64)
            else:
                self.x0 = np.asarray(x0, dtype=np.float64)
            self.jitter = None

    def phi(self, x: np.ndarray) -> np.ndarray:
        """
        Activation function phi(x) mapping synaptic input drive to firing rate (Hz).

        Sigmoidal: phi(x) = r_max / (1 + exp(-k * (x - x0)))
        Rectified Linear: phi(x) = clip(k * (x - x0), 0, r_max)
        """
        diff = x - self.x0
        if self.activation_type == "sigmoid":
            z = -self.gain_k * diff
            # Clamp exponent to prevent numerical underflow/overflow
            z = np.clip(z, -60.0, 60.0)
            return self.r_max / (1.0 + np.exp(z))
        elif self.activation_type in ("relu", "rectified_linear"):
            return np.clip(self.gain_k * diff, 0.0, self.r_max)
        else:
            raise ValueError(f"Unknown activation type: {self.activation_type}")

    def compute_synaptic_input(self, rates: np.ndarray) -> np.ndarray:
        """Computes total presynaptic drive h_i = sum_j W_ij * r_j * w_scale."""
        if len(self.row) == 0:
            return np.zeros(self.n, dtype=np.float64)

        # Fast vectorized sparse matrix-vector multiplication in pure NumPy
        # Edge contribution: W_ij * r_j
        contrib = self.data * rates[self.col]
        # Sum into postsynaptic row buckets
        syn_input = np.bincount(self.row, weights=contrib, minlength=self.n)
        return syn_input * self.w_scale

    def step(
        self,
        dt_ms: Optional[float] = None,
        stimulus_inputs: Optional[Sequence[Tuple[Any, Union[float, Callable[[float], float]]]]] = None,
        t_ms: float = 0.0,
        ext_current: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """
        Performs one forward Euler integration step of the continuous neural ODE:
            tau_i * dr_i/dt = -r_i + phi(sum_j W_ij * r_j + I_i^stim)

        Guarantees numerical stability and non-divergence within [0, r_max].
        """
        dt = float(dt_ms if dt_ms is not None else self.dt_ms)

        # 1. Total presynaptic synaptic drive
        syn_drive = self.compute_synaptic_input(self.r)

        # 2. Add external stimulus drive
        h = syn_drive
        if ext_current is not None:
            h = h + ext_current
        if self.jitter is not None:
            h = h * self.jitter

        # 3. Target firing rate via non-linear activation
        r_target = self.phi(h)

        # 4. Euler rate update with stability-bounded step factor alpha = min(1.0, dt / tau)
        alpha = np.clip(dt / np.maximum(self.tau, 1e-4), 0.0, 1.0)
        r_next = (1.0 - alpha) * self.r + alpha * r_target
        r_next = np.clip(r_next, 0.0, self.r_max)

        # 5. Drive forced sensory input classes if present
        if stimulus_inputs:
            for spec, rate_spec in stimulus_inputs:
                target_hz = rate_spec(t_ms) if callable(rate_spec) else float(rate_spec)
                ix = self.resolve_class(spec)
                if len(ix) > 0:
                    r_next[ix] = np.clip(np.maximum(r_next[ix], target_hz), 0.0, self.r_max)

        self.r = r_next
        return self.r

    def resolve_class(self, spec: Any) -> np.ndarray:
        """
        Resolves a class specification into an index array of matching neurons.

        Supported specs:
          - Explicit integer or integer array
          - String name in class_map or neuron_types (supports exact or prefix matching)
          - List of class names (union)
          - Dict specifying 'classes', optional 'side' ('L'/'R'), and/or 'receptorType'
          - List of dicts (union of specifications)
        """
        if isinstance(spec, (int, np.integer)):
            return np.array([int(spec)], dtype=int)

        if isinstance(spec, np.ndarray) and np.issubdtype(spec.dtype, np.integer):
            return spec

        if isinstance(spec, list) and spec and isinstance(spec[0], dict):
            resolved = [self.resolve_class(x) for x in spec]
            return np.unique(np.concatenate(resolved)) if resolved else np.empty(0, dtype=int)

        if isinstance(spec, dict):
            mask = np.ones(self.n, dtype=bool)
            if "receptorType" in spec and self.receptor_types is not None:
                mask &= np.char.find(self.receptor_types.astype(str), spec["receptorType"]) >= 0
            if "classes" in spec and self.neuron_types is not None:
                mask &= np.isin(self.neuron_types, spec["classes"])
            if spec.get("side") and self.soma_sides is not None:
                mask &= self.soma_sides == spec["side"]
            return np.flatnonzero(mask)

        if isinstance(spec, str):
            if spec in self.class_map:
                return self.class_map[spec]
            if self.neuron_types is not None:
                exact = np.flatnonzero(self.neuron_types == spec)
                if len(exact) > 0:
                    return exact
                # Prefix fallback (e.g. 'pC1' matches 'pC1a', 'pC1b')
                prefix_matches = np.flatnonzero(np.char.startswith(self.neuron_types.astype(str), spec))
                return prefix_matches
            return np.empty(0, dtype=int)

        if isinstance(spec, (list, tuple)):
            if not spec:
                return np.empty(0, dtype=int)
            if isinstance(spec[0], str):
                resolved = [self.resolve_class(s) for s in spec]
                return np.unique(np.concatenate(resolved)) if resolved else np.empty(0, dtype=int)
            return np.asarray(spec, dtype=int)

        return np.empty(0, dtype=int)

    def get_default_readouts(self) -> Dict[str, np.ndarray]:
        """Returns standard named readout neuron classes."""
        return {
            "DNp09": self.resolve_class("DNp09"),
            "MDN": self.resolve_class({"classes": ["MDN"]}),
            "DNp01": self.resolve_class("DNp01"),
            "pC1": self.resolve_class("pC1"),
            "pIP10": self.resolve_class("pIP10"),
            "HS_R": self.resolve_class({"classes": ["HSE", "HSN", "HSS"], "side": "R"}),
            "HS_L": self.resolve_class({"classes": ["HSE", "HSN", "HSS"], "side": "L"}),
            "DNa02_R": self.resolve_class({"classes": ["DNa02"], "side": "R"}),
            "DNa02_L": self.resolve_class({"classes": ["DNa02"], "side": "L"}),
        }

    def simulate(
        self,
        inputs: Optional[Sequence[Tuple[Any, Union[float, Callable[[float], float]]]]] = None,
        readouts: Optional[Dict[str, Any]] = None,
        warmup_ms: float = 300.0,
        baseline_ms: float = 300.0,
        stimulus_ms: float = 600.0,
        dt_ms: Optional[float] = None,
        bin_ms: float = 10.0,
        reset_state: bool = True,
        return_history: bool = False,
        track_trajectory: bool = True,
    ) -> Tuple[Dict[str, Dict[str, Any]], Optional[Dict[str, float]]]:
        """
        Executes a continuous trial across warmup, baseline, and stimulus windows.

        Parameters
        ----------
        inputs : list of (class_spec, rate_or_fn)
            Sensory input classes and their forced driving rates (Hz).
        readouts : dict of {name: class_spec}
            Descending and central readout classes to record.
        warmup_ms : float
            Warmup duration in ms (network settles to resting rate).
        baseline_ms : float
            Baseline recording duration in ms.
        stimulus_ms : float
            Stimulus duration in ms.
        dt_ms : float, optional
            Euler integration step size (ms). Defaults to self.dt_ms.
        bin_ms : float, default 10.0
            Temporal bin width (ms) for continuous trajectory rate series.
        reset_state : bool, default True
            Whether to reset firing rates to baseline before starting.
        return_history : bool, default False
            If True, returns full per-step rate histories as a third tuple element.
        track_trajectory : bool, default True
            Whether to track continuous 2D trajectory. When False, returns None for traj_metrics.

        Returns
        -------
        out : dict
            {readout_name: {'baseline_hz': float, 'stimulus_hz': float, 'n': int}}
        traj_metrics : dict or None
            Kinematic metrics from integrate_trajectory: displacement, path_length,
            forward_progress_index, straightness, turning_rate, angular_deviation.
        """
        dt = float(dt_ms if dt_ms is not None else self.dt_ms)
        if reset_state:
            self.r = np.full(self.n, self.r_baseline, dtype=np.float64)

        if readouts is None:
            readouts = self.get_default_readouts()

        # Pre-resolve readout indices
        resolved_readouts: Dict[str, np.ndarray] = {
            k: self.resolve_class(spec) for k, spec in readouts.items()
        }

        # Pre-resolve inputs
        resolved_inputs: List[Tuple[np.ndarray, Union[float, Callable[[float], float]]]] = []
        if inputs:
            for spec, r_spec in inputs:
                ix = self.resolve_class(spec)
                resolved_inputs.append((ix, r_spec))

        # Check trajectory tracking requirements
        desc_keys = ["DNp09", "MDN", "DNa02_L", "DNa02_R"]
        track_traj = track_trajectory and all(k in resolved_readouts and len(resolved_readouts[k]) > 0 for k in desc_keys)
        n_bins = max(1, int(round(stimulus_ms / bin_ms)))
        bin_rates = {k: np.zeros(n_bins, dtype=np.float64) for k in desc_keys} if track_traj else None

        # Cumulative window integrators
        baseline_integrals = {k: 0.0 for k in resolved_readouts}
        stimulus_integrals = {k: 0.0 for k in resolved_readouts}

        # Optional history recording
        history: Optional[Dict[str, List[float]]] = (
            {k: [] for k in resolved_readouts} if return_history else None
        )

        total_ms = warmup_ms + baseline_ms + stimulus_ms
        steps = int(round(total_ms / dt))

        for step_idx in range(steps):
            tm = step_idx * dt

            # Determine active inputs for this step
            active_inputs = None
            if tm >= warmup_ms + baseline_ms:
                active_inputs = []
                t_stim = tm - (warmup_ms + baseline_ms)
                for ix, r_spec in resolved_inputs:
                    target_hz = r_spec(t_stim) if callable(r_spec) else float(r_spec)
                    active_inputs.append((ix, target_hz))

            # Forward Euler step
            self.step(dt_ms=dt, stimulus_inputs=active_inputs, t_ms=tm)

            # Record metrics during baseline and stimulus windows
            if tm >= warmup_ms:
                in_baseline = tm < (warmup_ms + baseline_ms)
                for k, ix in resolved_readouts.items():
                    if len(ix) > 0:
                        class_mean_hz = float(np.mean(self.r[ix]))
                    else:
                        class_mean_hz = 0.0

                    if in_baseline:
                        baseline_integrals[k] += class_mean_hz * dt
                    else:
                        stimulus_integrals[k] += class_mean_hz * dt

                    if history is not None:
                        history[k].append(class_mean_hz)

                # Collect trajectory bins during stimulus window
                if track_traj and not in_baseline:
                    b_idx = int((tm - (warmup_ms + baseline_ms)) / bin_ms)
                    if 0 <= b_idx < n_bins:
                        for k in desc_keys:
                            ix = resolved_readouts[k]
                            bin_rates[k][b_idx] += float(np.mean(self.r[ix])) * (dt / bin_ms)

        # Assemble summary readout rates
        tb_sec = max(baseline_ms, 1e-4) / 1000.0
        ts_sec = max(stimulus_ms, 1e-4) / 1000.0

        out: Dict[str, Dict[str, Any]] = {}
        for k, ix in resolved_readouts.items():
            out[k] = {
                "baseline_hz": float(baseline_integrals[k] / max(baseline_ms, 1e-4)),
                "stimulus_hz": float(stimulus_integrals[k] / max(stimulus_ms, 1e-4)),
                "n": int(len(ix)),
            }

        # Integrate continuous 2D trajectory from descending firing rates
        traj_metrics = None
        if track_traj and bin_rates is not None:
            bin_sec = bin_ms / 1000.0
            rate_series = {k: bin_rates[k].tolist() for k in desc_keys}
            traj = integrate_trajectory(rate_series, dt=bin_sec)
            traj_metrics = trajectory_metrics(traj)

        if return_history:
            return out, traj_metrics, history  # type: ignore

        return out, traj_metrics

    def create_twin(self, condition: str = "shuffled", seed: Optional[int] = None) -> ConnectomeArenaSimulation:
        """Factory method creating a null twin instance with identical graph structure."""
        return ConnectomeArenaSimulation(
            weights=(self.row, self.col, self.data),
            signs=self.signs,
            num_neurons=self.n,
            neuron_types=self.neuron_types,
            soma_sides=self.soma_sides,
            receptor_types=self.receptor_types,
            body_ids=self.body_ids,
            class_map=self.class_map,
            tau_ms=self.tau,
            r_max=self.r_max,
            gain_k=self.gain_k,
            x0=self.x0,
            activation=self.activation_type,
            dt_ms=self.dt_ms,
            w_scale=self.w_scale,
            condition=condition,
            seed=seed,
            r_baseline=self.r_baseline,
        )

    @classmethod
    def from_substrate(
        cls,
        derived_dir: Optional[str] = None,
        data_dir: Optional[str] = None,
        condition: str = "real",
        seed: Optional[int] = None,
        **kwargs: Any,
    ) -> ConnectomeArenaSimulation:
        """
        Explicit factory method loading the G_traced connectome substrate from disk.
        Does not swallow missing file or library errors.
        """
        import os
        der = derived_dir or os.environ.get("FLY_DERIVED", "data/derived")
        data = data_dir or os.environ.get("FLY_DATA", "data/malecns")
        import scipy.sparse as sp
        import pyarrow.feather as pf
        import pyarrow.compute as pc

        ids = np.load(os.path.join(der, "G_traced_bodyIds.npy"))
        sign = np.load(os.path.join(der, "G_traced_presyn_sign.npy"))
        A = sp.load_npz(os.path.join(der, "G_traced_post_by_pre.npz")).tocoo()

        ann_path = os.path.join(data, "body-annotations-male-cns-v1.0-minconf-0.5.feather")
        ann = pf.read_table(ann_path, columns=["bodyId", "status", "type", "somaSide", "receptorType"])
        ann = ann.filter(pc.equal(ann.column("status"), "Traced")).to_pandas().set_index("bodyId").reindex(ids)

        typ = ann["type"].fillna("").to_numpy()
        side = ann["somaSide"].fillna("").to_numpy()
        rec = ann["receptorType"].fillna("").to_numpy()

        return cls(
            weights=A,
            signs=sign,
            num_neurons=len(ids),
            neuron_types=typ,
            soma_sides=side,
            receptor_types=rec,
            body_ids=ids,
            condition=condition,
            seed=seed,
            **kwargs,
        )

