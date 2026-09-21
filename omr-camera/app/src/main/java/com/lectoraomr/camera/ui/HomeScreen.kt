package com.lectoraomr.camera.ui

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CameraAlt
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.IosShare
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.runtime.LaunchedEffect
import androidx.lifecycle.Lifecycle
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import com.lectoraomr.camera.LotsViewModel
import com.lectoraomr.camera.data.Catalog
import com.lectoraomr.camera.data.ExportMode
import com.lectoraomr.camera.data.Lot
import com.lectoraomr.camera.data.ZipExporter
import com.lectoraomr.camera.ui.theme.Accent
import com.lectoraomr.camera.ui.theme.Ink
import com.lectoraomr.camera.ui.theme.InkHigh
import com.lectoraomr.camera.ui.theme.InkLift
import com.lectoraomr.camera.ui.theme.Line
import com.lectoraomr.camera.ui.theme.Mute
import com.lectoraomr.camera.ui.theme.Paper

@Composable
fun HomeScreen(
    vm: LotsViewModel,
    onScan: (salon: String, curso: String) -> Unit,
    onOpenLot: (Lot) -> Unit,
    onShareLast: (() -> Unit)?,
    onOpenSelected: () -> Unit
) {
    val salon by vm.salon.collectAsStateWithLifecycle()
    val curso by vm.curso.collectAsStateWithLifecycle()
    val lots by vm.lots.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val busyLabel by vm.busyLabel.collectAsStateWithLifecycle()
    val exportMessage by vm.exportMessage.collectAsStateWithLifecycle()
    val selectedCount = vm.countOf(salon, curso)
    val total = lots.sumOf { it.photoCount }
    var exportLots by remember { mutableStateOf<List<Lot>?>(null) }
    var deleteLot by remember { mutableStateOf<Lot?>(null) }
    val lifecycleOwner = LocalLifecycleOwner.current
    LaunchedEffect(lifecycleOwner) {
        lifecycleOwner.lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
            vm.refresh()
        }
    }

    Box(Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(Ink)
                .statusBarsPadding()
                .navigationBarsPadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 22.dp, vertical = 16.dp)
        ) {
            Text(
                "LECTORA OMR",
                style = androidx.compose.material3.MaterialTheme.typography.labelSmall,
                color = Accent,
                letterSpacing = 2.4.sp
            )
            Spacer(Modifier.height(6.dp))
            Text("Cámara de fichas", fontSize = 28.sp, fontWeight = FontWeight.SemiBold, color = Paper, letterSpacing = (-0.5).sp)
            Text(
                "Captura A5 por sección y curso. Exporta ZIP o carpetas a Descargas / LectoraOMR.",
                color = Mute,
                fontSize = 14.sp,
                lineHeight = 20.sp,
                modifier = Modifier.padding(top = 6.dp)
            )

            Spacer(Modifier.height(28.dp))
            Label("Sección")
            Spacer(Modifier.height(10.dp))
            Row(
                Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Catalog.secciones.forEach { s ->
                    Chip(s, selected = s == salon) { vm.setSalon(s) }
                }
            }

            Spacer(Modifier.height(22.dp))
            Label("Curso")
            Spacer(Modifier.height(10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                Catalog.cursos.forEach { c ->
                    CursoCard(
                        title = c.label,
                        count = vm.countOf(salon, c.id),
                        selected = c.id == curso,
                        modifier = Modifier.weight(1f)
                    ) { vm.setCurso(c.id) }
                }
            }

            Spacer(Modifier.height(22.dp))
            if (selectedCount > 0) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    PrimaryButton(
                        text = "Escanear",
                        icon = true,
                        modifier = Modifier.weight(1.25f)
                    ) { onScan(salon, curso) }
                    Box(
                        Modifier
                            .weight(1f)
                            .height(54.dp)
                            .clip(RoundedCornerShape(16.dp))
                            .background(InkHigh)
                            .clickable(onClick = onOpenSelected),
                        contentAlignment = Alignment.Center
                    ) {
                        Text("Ver lote  ·  $selectedCount", color = Paper, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                    }
                }
            } else {
                PrimaryButton(
                    text = "Escanear  ·  $salon  ·  ${Catalog.cursoLabel(curso)}",
                    icon = true
                ) { onScan(salon, curso) }
            }
            Text(
                if (selectedCount == 0) "Este lote está vacío" else "$salon  ·  ${Catalog.cursoLabel(curso)}",
                color = Mute,
                fontSize = 12.sp,
                modifier = Modifier
                    .padding(top = 10.dp)
                    .align(Alignment.CenterHorizontally)
            )

            Spacer(Modifier.height(32.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Label("Lotes")
                if (total > 0) {
                    Text(
                        "Exportar todos",
                        color = Accent,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Medium,
                        modifier = Modifier.clickable { exportLots = lots }
                    )
                }
            }
            Spacer(Modifier.height(10.dp))
            if (lots.isEmpty()) {
                Box(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(16.dp))
                        .background(InkLift)
                        .padding(22.dp)
                ) {
                    Text("Todavía no hay fotos. Elige sección y curso, y escanea.", color = Mute, fontSize = 14.sp)
                }
            } else {
                lots.forEach { lot ->
                    LotRow(
                        lot = lot,
                        onOpen = { onOpenLot(lot) },
                        onExport = { exportLots = listOf(lot) },
                        onDelete = { deleteLot = lot }
                    )
                    Spacer(Modifier.height(8.dp))
                }
            }

            if (!exportMessage.isNullOrBlank()) {
                Spacer(Modifier.height(14.dp))
                Column(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(14.dp))
                        .background(Accent.copy(alpha = 0.12f))
                        .padding(14.dp)
                ) {
                    Text(exportMessage ?: "", color = Paper, fontSize = 13.sp)
                    if (onShareLast != null) {
                        Spacer(Modifier.height(8.dp))
                        Text(
                            "Compartir este ZIP",
                            color = Accent,
                            fontWeight = FontWeight.Medium,
                            fontSize = 13.sp,
                            modifier = Modifier.clickable { onShareLast() }
                        )
                    }
                }
            }
            CreditsFooter()
            Spacer(Modifier.height(8.dp))
        }

        if (busy) {
            Box(
                Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = 0.45f)),
                contentAlignment = Alignment.Center
            ) {
                Column(
                    Modifier
                        .clip(RoundedCornerShape(16.dp))
                        .background(InkLift)
                        .padding(horizontal = 28.dp, vertical = 22.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    CircularProgressIndicator(color = Accent, strokeWidth = 2.dp, modifier = Modifier.size(28.dp))
                    Spacer(Modifier.height(12.dp))
                    Text(busyLabel.ifBlank { "Trabajando…" }, color = Paper, fontSize = 14.sp)
                }
            }
        }
    }

    exportLots?.let { target ->
        PackExportDialog(
            title = if (target.size == 1) "Exportar lote" else "Exportar todos",
            defaultName = ZipExporter.defaultPackName(),
            onDismiss = { exportLots = null },
            onConfirm = { name, mode ->
                val list = target
                exportLots = null
                vm.exportPack(list, name, mode) {}
            }
        )
    }
    deleteLot?.let { lot ->
        ConfirmDialog(
            title = "Eliminar lote",
            body = "Se borrarán ${lot.photoCount} fichas de ${lot.salon} · ${lot.title}. No se puede deshacer.",
            confirm = "Eliminar",
            danger = true,
            onConfirm = {
                vm.deleteLot(lot.salon, lot.curso)
                deleteLot = null
            },
            onDismiss = { deleteLot = null }
        )
    }
}

@Composable
private fun Label(text: String) {
    Text(
        text.uppercase(),
        color = Mute,
        fontSize = 11.sp,
        fontWeight = FontWeight.Medium,
        letterSpacing = 1.4.sp
    )
}

@Composable
private fun Chip(text: String, selected: Boolean, onClick: () -> Unit) {
    val bg by animateColorAsState(if (selected) Accent else InkLift, tween(120), label = "chip")
    val fg by animateColorAsState(if (selected) Ink else Paper, tween(120), label = "chipFg")
    Box(
        Modifier
            .clip(RoundedCornerShape(20.dp))
            .background(bg)
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 8.dp)
    ) {
        Text(text, color = fg, fontSize = 13.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun CursoCard(title: String, count: Int, selected: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Column(
        modifier
            .clip(RoundedCornerShape(18.dp))
            .background(if (selected) Accent.copy(alpha = 0.12f) else InkLift)
            .border(1.dp, if (selected) Accent else Color.Transparent, RoundedCornerShape(18.dp))
            .clickable(onClick = onClick)
            .padding(16.dp)
    ) {
        Text(title, color = Paper, fontWeight = FontWeight.Medium, fontSize = 16.sp)
        Spacer(Modifier.height(6.dp))
        Text("$count fotos", color = Mute, fontSize = 12.sp)
    }
}

@Composable
private fun PrimaryButton(
    text: String,
    icon: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    Row(
        modifier
            .fillMaxWidth()
            .height(54.dp)
            .clip(RoundedCornerShape(16.dp))
            .background(Accent)
            .clickable(onClick = onClick),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center
    ) {
        if (icon) {
            Icon(Icons.Outlined.CameraAlt, contentDescription = null, tint = Ink, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
        }
        Text(text, color = Ink, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
    }
}

@Composable
private fun LotRow(lot: Lot, onOpen: () -> Unit, onExport: () -> Unit, onDelete: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(InkLift)
            .clickable(onClick = onOpen)
            .padding(horizontal = 16.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(Modifier.weight(1f)) {
            Text("${lot.salon}  ·  ${lot.title}", color = Paper, fontWeight = FontWeight.Medium, fontSize = 15.sp)
            Text("${lot.photoCount} fichas", color = Mute, fontSize = 12.sp, modifier = Modifier.padding(top = 2.dp))
        }
        Box(
            Modifier
                .size(40.dp)
                .clip(CircleShape)
                .background(InkHigh)
                .clickable(onClick = onExport),
            contentAlignment = Alignment.Center
        ) {
            Icon(Icons.Outlined.IosShare, contentDescription = "Exportar", tint = Accent, modifier = Modifier.size(18.dp))
        }
        Spacer(Modifier.width(6.dp))
        Box(
            Modifier
                .size(40.dp)
                .clip(CircleShape)
                .background(InkHigh)
                .clickable(onClick = onDelete),
            contentAlignment = Alignment.Center
        ) {
            Icon(Icons.Outlined.Delete, contentDescription = "Eliminar lote", tint = Mute, modifier = Modifier.size(18.dp))
        }
        Spacer(Modifier.width(6.dp))
        Icon(Icons.Outlined.ChevronRight, contentDescription = null, tint = Mute, modifier = Modifier.size(20.dp))
    }
}
