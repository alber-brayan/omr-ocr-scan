package com.lectoraomr.camera.camera

data class CornerHits(
    val tl: Boolean = false,
    val tr: Boolean = false,
    val bl: Boolean = false,
    val br: Boolean = false
) {
    val count: Int get() = listOf(tl, tr, bl, br).count { it }
    val missing: List<String>
        get() = buildList {
            if (!tl) add("sup. izq. ■")
            if (!tr) add("sup. der. ▢")
            if (!bl) add("inf. izq. ●")
            if (!br) add("inf. der. ⌞")
        }
}

data class SheetQuality(
    val sharpness: Float = 0f,
    val brightness: Float = 0f,
    val fill: Float = 0f,
    val corners: CornerHits = CornerHits(),
    val hint: String = "Encaja la ficha en el recuadro",
    val ready: Boolean = false,
    val imageAspect: Float = 3f / 4f
) {
    val level: Level
        get() = when {
            ready -> Level.Go
            corners.count >= 2 -> Level.Almost
            else -> Level.Stop
        }

    enum class Level { Stop, Almost, Go }
}
