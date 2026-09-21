package com.lectoraomr.camera

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.lectoraomr.camera.data.Catalog
import com.lectoraomr.camera.data.ExportMode
import com.lectoraomr.camera.data.ExportResult
import com.lectoraomr.camera.data.Lot
import com.lectoraomr.camera.data.LotRepository
import com.lectoraomr.camera.data.ZipExporter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class LotsViewModel(app: Application) : AndroidViewModel(app) {
    val repo: LotRepository = (app as OmrCameraApp).repo

    private val _salon = MutableStateFlow(Catalog.secciones.first())
    val salon: StateFlow<String> = _salon.asStateFlow()

    private val _curso = MutableStateFlow(Catalog.cursos.first().id)
    val curso: StateFlow<String> = _curso.asStateFlow()

    private val _lots = MutableStateFlow<List<Lot>>(emptyList())
    val lots: StateFlow<List<Lot>> = _lots.asStateFlow()

    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy.asStateFlow()

    private val _busyLabel = MutableStateFlow("")
    val busyLabel: StateFlow<String> = _busyLabel.asStateFlow()

    private val _exportMessage = MutableStateFlow<String?>(null)
    val exportMessage: StateFlow<String?> = _exportMessage.asStateFlow()

    private val _lastExportUri = MutableStateFlow<Uri?>(null)
    val lastExportUri: StateFlow<Uri?> = _lastExportUri.asStateFlow()

    private val _lastExportName = MutableStateFlow("")
    val lastExportName: StateFlow<String> = _lastExportName.asStateFlow()

    init {
        refresh()
    }

    fun setSalon(v: String) {
        _salon.value = v
    }

    fun setCurso(v: String) {
        _curso.value = v
    }

    fun refresh() {
        _lots.value = repo.listLots()
    }

    fun countOf(salon: String, curso: String): Int =
        _lots.value.firstOrNull {
            it.salon.equals(salon, ignoreCase = true) && it.curso.equals(curso, ignoreCase = true)
        }?.photoCount ?: 0

    fun deleteLot(salon: String, curso: String) {
        viewModelScope.launch(Dispatchers.IO) {
            repo.deleteLot(salon, curso)
            _lots.value = repo.listLots()
        }
    }

    fun exportPack(lots: List<Lot>, name: String, mode: ExportMode, onDone: (ExportResult) -> Unit) {
        viewModelScope.launch {
            _busy.value = true
            _busyLabel.value = if (mode == ExportMode.ZIP) "Creando ZIP…" else "Copiando carpetas…"
            val result = withContext(Dispatchers.IO) {
                ZipExporter.exportPack(getApplication(), repo, lots, name, mode)
            }
            _busy.value = false
            _busyLabel.value = ""
            if (result.ok) {
                _lastExportUri.value = result.uri
                _lastExportName.value = result.name
                _exportMessage.value = if (mode == ExportMode.ZIP) {
                    "ZIP: ${result.folderLabel}/${result.name}"
                } else {
                    "Carpetas: ${result.folderLabel}"
                }
            } else {
                _lastExportUri.value = null
                _exportMessage.value = "No hay fotos para exportar"
            }
            onDone(result)
        }
    }
}
