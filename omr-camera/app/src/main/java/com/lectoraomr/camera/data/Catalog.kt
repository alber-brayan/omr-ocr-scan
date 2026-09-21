package com.lectoraomr.camera.data

data class Curso(val id: String, val label: String)

object Catalog {
    val secciones = listOf(
        "Sec 1", "Sec 2", "Sec 3", "Sec 4", "Sec 5",
        "Prim 2", "Prim 3", "Prim 4", "Prim 5", "Prim 6"
    )
    val cursos = listOf(
        Curso("Matematica", "Matemática"),
        Curso("Comunicacion", "Comunicación")
    )

    fun cursoLabel(id: String): String =
        cursos.firstOrNull { it.id == id }?.label ?: id

    fun safeName(raw: String): String =
        raw.trim()
            .replace(Regex("""[\\/:*?"<>|]"""), "-")
            .ifBlank { "SinNombre" }
}

data class Lot(
    val salon: String,
    val curso: String,
    val photoCount: Int,
    val dir: java.io.File
) {
    val title: String get() = "${Catalog.cursoLabel(curso)}"
    val subtitle: String get() = salon
}
