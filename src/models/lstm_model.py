"""Red neuronal LSTM en PyTorch.

**Por qué PyTorch y no TensorFlow/Keras**

1. *Soporte de Python 3.13*: PyTorch lo soporta desde la 2.6; TensorFlow llegó
   más tarde y en Windows su instalación es frágil.
2. *Peso*: la rueda de PyTorch CPU ronda los 200 MB frente a ~600 MB de
   TensorFlow. Para un trabajo de grado que el jurado debe poder instalar en
   cualquier equipo, eso importa.
3. *GPU en Windows*: TensorFlow abandonó el soporte nativo de GPU en Windows a
   partir de la 2.11 (obliga a WSL2). PyTorch lo mantiene.
4. El código de una LSTM es prácticamente igual de corto en ambos.

**Por qué una LSTM aquí**

Los modelos de árboles ven cada fila de forma independiente: la secuencia solo
les llega a través de los rezagos que le construimos a mano. Una LSTM procesa
la ventana temporal completa y aprende ella misma qué recordar y qué olvidar
mediante sus puertas. La comparación honesta entre ambos enfoques es justo una
de las aportaciones del trabajo.

**Diferencia clave de preparación**: la LSTM sí necesita entrada escalada (las
funciones de activación saturan con valores grandes) y una forma tridimensional
`(muestras, pasos_temporales, variables)`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler
from torch import nn

from src.core.logging import get_logger
from src.models.base import ModeloPredictivo

log = get_logger(__name__)


class _RedLSTM(nn.Module):
    """LSTM apilada + capa densa de salida."""

    def __init__(
        self,
        n_features: int,
        unidades: int = 64,
        capas: int = 2,
        dropout: float = 0.2,
    ) -> None:
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=n_features,
            hidden_size=unidades,
            num_layers=capas,
            batch_first=True,
            # PyTorch ignora dropout si num_layers == 1 y emite un aviso.
            dropout=dropout if capas > 1 else 0.0,
        )
        self.dropout = nn.Dropout(dropout)
        self.salida = nn.Linear(unidades, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        salida_secuencia, _ = self.lstm(x)
        # Solo interesa el último paso temporal: resume toda la ventana.
        ultimo = salida_secuencia[:, -1, :]
        return self.salida(self.dropout(ultimo)).squeeze(-1)


class ModeloLSTM(ModeloPredictivo):
    """LSTM para regresión sobre ventanas temporales."""

    nombre = "lstm"

    def __init__(
        self,
        ventana: int = 24,
        unidades: int = 64,
        capas: int = 2,
        dropout: float = 0.2,
        epocas: int = 40,
        batch_size: int = 64,
        learning_rate: float = 1e-3,
        paciencia: int = 7,
        proporcion_validacion: float = 0.1,
        random_state: int = 42,
        **kwargs,
    ) -> None:
        super().__init__(
            ventana=ventana,
            unidades=unidades,
            capas=capas,
            dropout=dropout,
            epocas=epocas,
            batch_size=batch_size,
            learning_rate=learning_rate,
            **kwargs,
        )
        self.ventana = ventana
        self.unidades = unidades
        self.capas = capas
        self.dropout = dropout
        self.epocas = epocas
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.paciencia = paciencia
        self.proporcion_validacion = proporcion_validacion
        self.random_state = random_state

        self.escalador_X = StandardScaler()
        self.escalador_y = StandardScaler()
        self.red: _RedLSTM | None = None
        self.dispositivo = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # -- Entrenamiento ------------------------------------------------------

    def fit(self, X: pd.DataFrame, y: pd.Series | np.ndarray) -> ModeloLSTM:
        torch.manual_seed(self.random_state)
        np.random.seed(self.random_state)

        self.columnas_features = list(X.columns)
        y = np.asarray(y, dtype=float).reshape(-1, 1)

        if len(X) <= self.ventana + 1:
            raise ValueError(
                f"Se necesitan más de {self.ventana + 1} muestras para una ventana "
                f"de {self.ventana}; se recibieron {len(X)}"
            )

        X_esc = self.escalador_X.fit_transform(X.to_numpy(dtype=float))
        y_esc = self.escalador_y.fit_transform(y).ravel()

        X_seq, y_seq = _crear_secuencias(X_esc, y_esc, self.ventana)

        # Split cronológico para la parada temprana.
        corte = max(1, int(len(X_seq) * (1 - self.proporcion_validacion)))
        X_tr = torch.tensor(X_seq[:corte], dtype=torch.float32, device=self.dispositivo)
        y_tr = torch.tensor(y_seq[:corte], dtype=torch.float32, device=self.dispositivo)
        X_val = torch.tensor(X_seq[corte:], dtype=torch.float32, device=self.dispositivo)
        y_val = torch.tensor(y_seq[corte:], dtype=torch.float32, device=self.dispositivo)

        self.red = _RedLSTM(
            n_features=X_seq.shape[2],
            unidades=self.unidades,
            capas=self.capas,
            dropout=self.dropout,
        ).to(self.dispositivo)

        optimizador = torch.optim.Adam(self.red.parameters(), lr=self.learning_rate)
        criterio = nn.MSELoss()

        mejor_perdida = float("inf")
        mejores_pesos = None
        epocas_sin_mejora = 0
        n = len(X_tr)

        for epoca in range(1, self.epocas + 1):
            self.red.train()
            permutacion = torch.randperm(n, device=self.dispositivo)
            perdida_acumulada = 0.0

            for inicio in range(0, n, self.batch_size):
                indices = permutacion[inicio : inicio + self.batch_size]
                optimizador.zero_grad()
                perdida = criterio(self.red(X_tr[indices]), y_tr[indices])
                perdida.backward()
                # Recorte de gradiente: las LSTM son propensas a gradientes
                # explosivos en secuencias largas.
                nn.utils.clip_grad_norm_(self.red.parameters(), max_norm=1.0)
                optimizador.step()
                perdida_acumulada += perdida.item() * len(indices)

            perdida_val = self._perdida_validacion(X_val, y_val, criterio)
            if epoca % 5 == 0 or epoca == 1:
                log.info(
                    "LSTM época %2d/%d  train=%.5f  val=%.5f",
                    epoca,
                    self.epocas,
                    perdida_acumulada / n,
                    perdida_val,
                )

            if perdida_val < mejor_perdida - 1e-6:
                mejor_perdida = perdida_val
                mejores_pesos = {k: v.detach().clone() for k, v in self.red.state_dict().items()}
                epocas_sin_mejora = 0
            else:
                epocas_sin_mejora += 1
                if epocas_sin_mejora >= self.paciencia:
                    log.info("LSTM: parada temprana en la época %d", epoca)
                    break

        if mejores_pesos is not None:
            self.red.load_state_dict(mejores_pesos)

        self.entrenado = True
        return self

    def _perdida_validacion(
        self, X_val: torch.Tensor, y_val: torch.Tensor, criterio: nn.Module
    ) -> float:
        if len(X_val) == 0:
            return float("inf")
        assert self.red is not None
        self.red.eval()
        with torch.no_grad():
            return float(criterio(self.red(X_val), y_val).item())

    # -- Predicción ---------------------------------------------------------

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predice para cada fila de `X`.

        Las primeras `ventana` filas no tienen historia suficiente para formar
        una secuencia completa. En vez de devolver menos predicciones que filas
        —lo que rompería la comparación con los demás modelos— se rellenan con
        la primera predicción válida (*padding* hacia atrás). El efecto sobre
        las métricas es despreciable con miles de filas y mantiene alineadas
        las salidas de todos los modelos.
        """
        self._verificar_entrenado()
        assert self.red is not None

        X_alineado = self._alinear_columnas(X)
        X_esc = self.escalador_X.transform(X_alineado.to_numpy(dtype=float))

        if len(X_esc) <= self.ventana:
            raise ValueError(
                f"Se necesitan más de {self.ventana} filas para predecir; "
                f"se recibieron {len(X_esc)}"
            )

        secuencias = np.lib.stride_tricks.sliding_window_view(
            X_esc, window_shape=self.ventana, axis=0
        ).transpose(0, 2, 1)[:-1]

        self.red.eval()
        predicciones: list[np.ndarray] = []
        with torch.no_grad():
            for inicio in range(0, len(secuencias), 512):
                lote = torch.tensor(
                    secuencias[inicio : inicio + 512],
                    dtype=torch.float32,
                    device=self.dispositivo,
                )
                predicciones.append(self.red(lote).cpu().numpy())

        y_esc = np.concatenate(predicciones).reshape(-1, 1)
        y = self.escalador_y.inverse_transform(y_esc).ravel()

        relleno = np.full(self.ventana, y[0])
        return np.concatenate([relleno, y])

    # -- Serialización ------------------------------------------------------

    def __getstate__(self) -> dict:
        """`torch.device` no siempre se serializa bien; se guarda como texto."""
        estado = self.__dict__.copy()
        estado["dispositivo"] = str(self.dispositivo)
        if self.red is not None:
            estado["red"] = {
                "state_dict": {k: v.cpu() for k, v in self.red.state_dict().items()},
                "n_features": self.red.lstm.input_size,
            }
        return estado

    def __setstate__(self, estado: dict) -> None:
        red_serializada = estado.pop("red", None)
        self.__dict__.update(estado)
        self.dispositivo = torch.device(
            "cuda" if torch.cuda.is_available() and "cuda" in str(estado.get("dispositivo")) else "cpu"
        )

        if isinstance(red_serializada, dict):
            self.red = _RedLSTM(
                n_features=red_serializada["n_features"],
                unidades=self.unidades,
                capas=self.capas,
                dropout=self.dropout,
            ).to(self.dispositivo)
            self.red.load_state_dict(red_serializada["state_dict"])
            self.red.eval()
        else:
            self.red = red_serializada


# ---------------------------------------------------------------------------


def _crear_secuencias(
    X: np.ndarray, y: np.ndarray, ventana: int
) -> tuple[np.ndarray, np.ndarray]:
    """Convierte una matriz 2D en secuencias 3D `(n, ventana, features)`.

    La secuencia ``i`` contiene las filas ``[i, i+ventana)`` y su etiqueta es
    ``y[i + ventana]``: se predice siempre con información estrictamente
    anterior al instante etiquetado.
    """
    secuencias = np.lib.stride_tricks.sliding_window_view(
        X, window_shape=ventana, axis=0
    ).transpose(0, 2, 1)[:-1]
    etiquetas = y[ventana:]
    return np.ascontiguousarray(secuencias), np.ascontiguousarray(etiquetas)
