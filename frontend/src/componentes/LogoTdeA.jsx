/**
 * Logo institucional del Tecnológico de Antioquia.
 *
 * Es el archivo **oficial sin retocar** (`public/tdea.svg`, descargado del sitio
 * de la institución). No se le cambia ni un color: la marca de una institución
 * no es un elemento de diseño que este proyecto pueda ajustar a su paleta.
 *
 * De ahí la placa clara. El logo es verde oscuro sobre transparente y el tablero
 * es oscuro: puesto directamente, el nombre "TdeA" queda con un contraste
 * cercano a 2:1, ilegible. La alternativa habitual sería una versión blanca del
 * logo, pero la institución no publica ninguna, así que se le pone debajo la
 * superficie clara para la que fue diseñado. Es lo que hace cualquier impreso
 * que coloca un logo a color sobre un fondo oscuro.
 *
 * Al imprimir no hace falta: el informe ya va sobre blanco (ver
 * `estilos/informe.css`, que quita la placa).
 */

const ALTURAS = {
  barra: 24,
  tarjeta: 34,
  informe: 30,
};

export default function LogoTdeA({ tamano = "barra", conPlaca = true }) {
  const alto = ALTURAS[tamano] ?? ALTURAS.barra;

  return (
    <span className={`logo-tdea${conPlaca ? " logo-tdea--placa" : ""}`}>
      <img
        src="/tdea.svg"
        alt="Tecnológico de Antioquia, Institución Universitaria"
        height={alto}
        style={{ height: alto }}
        /* El logo no aporta nada mientras se lee el resto: que cargue cuando
           toque y no compita por el ancho de banda con los datos. */
        loading="lazy"
        decoding="async"
      />
    </span>
  );
}
