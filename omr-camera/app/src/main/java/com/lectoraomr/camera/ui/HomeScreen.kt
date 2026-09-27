package com.lectoraomr.camera.ui

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoStories
import androidx.compose.material.icons.outlined.CameraAlt
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.Functions
import androidx.compose.material.icons.outlined.IosShare
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import com.lectoraomr.camera.LotsViewModel
import com.lectoraomr.camera.data.Catalog
import com.lectoraomr.camera.data.Lot
import com.lectoraomr.camera.data.ZipExporter
import com.lectoraomr.camera.ui.theme.Accent
import com.lectoraomr.camera.ui.theme.AccentGradient
import com.lectoraomr.camera.ui.theme.AppBackdrop
import com.lectoraomr.camera.ui.theme.ElectricBlue
import com.lectoraomr.camera.ui.theme.ElectricViolet
import com.lectoraomr.camera.ui.theme.Ink
import com.lectoraomr.camera.ui.theme.InkHigh
import com.lectoraomr.camera.ui.theme.InkLift
import com.lectoraomr.camera.ui.theme.Line
import com.lectoraomr.camera.ui.theme.Mute
import com.lectoraomr.camera.ui.theme.Paper
import com.lectoraomr.camera.ui.theme.proPanel

@OptIn(ExperimentalLayoutApi::class)
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
    val reveal = remember { Animatable(0f) }

    LaunchedEffect(Unit) {
        reveal.animateTo(1f, tween(480))
    }
    LaunchedEffect(lifecycleOwner) {
        lifecycleOwner.lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
            vm.refresh()
        }
    }

    AppBackdrop(Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .statusBarsPadding()
                .navigationBarsPadding()
                .verticalScroll(rememberScrollState())
                .graphicsLayer {
                    alpha = 0.35f + 0.65f * reveal.value
                    translationY = (1f - reveal.value) * 26f
                }
                .padding(horizontal = 18.dp, vertical = 14.dp)
        ) {
            OmrHero(total)

            Spacer(Modifier.height(26.dp))
            SectionLabel("Configuración de captura", "01")
            Spacer(Modifier.height(12.dp))
            Text("Sección", color = Mute, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(9.dp))
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Catalog.secciones.forEach { s ->
                    Chip(s, selected = s == salon) { vm.setSalon(s) }
                }
            }

            Spacer(Modifier.height(20.dp))
            Text("Curso", color = Mute, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(9.dp))
            Column(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                Catalog.cursos.forEachIndexed { index, c ->
                    CursoRow(
                        title = c.label,
                        count = vm.countOf(salon, c.id),
                        selected = c.id == curso,
                        iconMath = index == 0
                    ) { vm.setCurso(c.id) }
                }
            }

            Spacer(Modifier.height(18.dp))
            PrimaryButton(
                text = if (selectedCount > 0) "Escanear" else "Escanear · $salon"
            ) { onScan(salon, curso) }
            if (selectedCount > 0) {
                Spacer(Modifier.height(10.dp))
                SecondaryButton(
                    text = "Ver lote · $selectedCount",
                    modifier = Modifier.fillMaxWidth(),
                    onClick = onOpenSelected
                )
            }
            Text(
                "$salon  ·  ${Catalog.cursoLabel(curso)}  ·  ${if (selectedCount == 0) "lote vacío" else "$selectedCount fichas"}",
                color = Mute,
                fontSize = 11.sp,
                modifier = Modifier.padding(top = 10.dp).align(Alignment.CenterHorizontally)
            )

            Spacer(Modifier.height(30.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                SectionLabel("Lotes guardados", "02")
                if (total > 0) {
                    Text(
                        "EXPORTAR TODOS",
                        color = Accent,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 1.1.sp,
                        modifier = Modifier
                            .clip(RoundedCornerShape(10.dp))
                            .clickable { exportLots = lots }
                            .padding(horizontal = 8.dp, vertical = 6.dp)
                    )
                }
            }
            Spacer(Modifier.height(11.dp))
            if (lots.isEmpty()) {
                Column(
                    Modifier
                        .fillMaxWidth()
                        .proPanel(radius = 18.dp, elevation = 8.dp)
                        .padding(20.dp)
                ) {
                    Text("Tu primer lote comienza aquí", color = Paper, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
                    Text(
                        "Elige una sección y un curso; la lectora organizará cada ficha automáticamente.",
                        color = Mute,
                        fontSize = 13.sp,
                        lineHeight = 19.sp,
                        modifier = Modifier.padding(top = 5.dp)
                    )
                }
            } else {
                lots.forEach { lot ->
                    LotRow(
                        lot = lot,
                        onOpen = { onOpenLot(lot) },
                        onExport = { exportLots = listOf(lot) },
                        onDelete = { deleteLot = lot }
                    )
                    Spacer(Modifier.height(9.dp))
                }
            }

            if (!exportMessage.isNullOrBlank()) {
                Spacer(Modifier.height(14.dp))
                Column(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(16.dp))
                        .background(Accent.copy(alpha = 0.1f))
                        .border(1.dp, Accent.copy(alpha = 0.22f), RoundedCornerShape(16.dp))
                        .padding(15.dp)
                ) {
                    Text(exportMessage ?: "", color = Paper, fontSize = 13.sp)
                    if (onShareLast != null) {
                        Text(
                            "COMPARTIR ZIP",
                            color = Accent,
                            fontWeight = FontWeight.Bold,
                            fontSize = 10.sp,
                            letterSpacing = 1.sp,
                            modifier = Modifier.padding(top = 9.dp).clickable { onShareLast() }
                        )
                    }
                }
            }
            CreditsFooter()
            Spacer(Modifier.height(8.dp))
        }

        if (busy) {
            Box(
                Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.62f)),
                contentAlignment = Alignment.Center
            ) {
                Column(
                    Modifier
                        .padding(30.dp)
                        .proPanel(radius = 22.dp, elevation = 24.dp)
                        .padding(horizontal = 34.dp, vertical = 26.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    CircularProgressIndicator(color = Accent, strokeWidth = 2.dp, modifier = Modifier.size(30.dp))
                    Spacer(Modifier.height(14.dp))
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
private fun OmrHero(total: Int) {
    val infinite = rememberInfiniteTransition(label = "scanner")
    val floatY by infinite.animateFloat(
        initialValue = 6f,
        targetValue = -8f,
        animationSpec = infiniteRepeatable(tween(2400), RepeatMode.Reverse),
        label = "scannerFloat"
    )
    val beam by infinite.animateFloat(
        initialValue = 0.16f,
        targetValue = 0.82f,
        animationSpec = infiniteRepeatable(tween(2800), RepeatMode.Reverse),
        label = "scanBeam"
    )
    val orbit by infinite.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(tween(7000, easing = LinearEasing)),
        label = "orbit"
    )
    val orbitBack by infinite.animateFloat(
        initialValue = 360f,
        targetValue = 0f,
        animationSpec = infiniteRepeatable(tween(5200, easing = LinearEasing)),
        label = "orbitBack"
    )
    val pulse by infinite.animateFloat(
        initialValue = 0.72f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(1200), RepeatMode.Reverse),
        label = "statusPulse"
    )
    Column(
        Modifier
            .fillMaxWidth()
            .proPanel(
                radius = 28.dp,
                elevation = 22.dp,
                borderColor = Accent.copy(alpha = 0.22f),
                brush = Brush.linearGradient(
                    listOf(Color(0xF21B3150), Color(0xF20B1428), Color(0xF2131735))
                )
            )
            .padding(start = 22.dp, end = 22.dp, top = 22.dp, bottom = 8.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(8.dp)
                    .graphicsLayer {
                        scaleX = 0.9f + pulse * 0.2f
                        scaleY = 0.9f + pulse * 0.2f
                        alpha = pulse
                    }
                    .shadow(10.dp, CircleShape)
                    .clip(CircleShape)
                    .background(Accent)
            )
            Spacer(Modifier.width(8.dp))
            Text("SISTEMA LISTO", color = Accent, fontSize = 9.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.4.sp)
            Spacer(Modifier.width(8.dp))
            Text(
                "RED LOCAL",
                color = ElectricViolet,
                fontSize = 9.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 1.1.sp,
                modifier = Modifier
                    .clip(RoundedCornerShape(99.dp))
                    .background(ElectricViolet.copy(alpha = 0.12f))
                    .border(1.dp, ElectricViolet.copy(alpha = 0.28f), RoundedCornerShape(99.dp))
                    .padding(horizontal = 8.dp, vertical = 4.dp)
            )
        }
        Spacer(Modifier.height(16.dp))
        Text("LECTORA", color = Paper, style = MaterialTheme.typography.displaySmall)
        Text(
            "OMR",
            style = MaterialTheme.typography.displaySmall.copy(
                brush = Brush.linearGradient(
                    listOf(Color(0xFF5EEAD4), Color(0xFF38BDF8), Color(0xFFA78BFA))
                )
            )
        )
        Text(
            "Captura precisa y lotes listos para calificar.",
            color = Mute,
            fontSize = 13.sp,
            lineHeight = 19.sp,
            modifier = Modifier.padding(top = 8.dp)
        )
        Spacer(Modifier.height(14.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HeroMetric("01", "$total fichas")
            HeroMetric("A5", "formato")
        }
        ScannerStage(
            floatY = floatY,
            beam = beam,
            orbit = orbit,
            orbitBack = orbitBack,
            modifier = Modifier
                .fillMaxWidth()
                .height(214.dp)
        )
    }
}

@Composable
private fun ScannerStage(
    floatY: Float,
    beam: Float,
    orbit: Float,
    orbitBack: Float,
    modifier: Modifier = Modifier
) {
    Box(modifier, contentAlignment = Alignment.Center) {
        Box(
            Modifier
                .size(width = 228.dp, height = 108.dp)
                .graphicsLayer {
                    rotationX = 66f
                    rotationZ = orbit
                    cameraDistance = 16f * density
                }
                .border(1.dp, Accent.copy(alpha = 0.28f), RoundedCornerShape(50))
        )
        Box(
            Modifier
                .size(width = 176.dp, height = 82.dp)
                .graphicsLayer {
                    rotationX = 66f
                    rotationZ = orbitBack
                    cameraDistance = 16f * density
                }
                .border(1.dp, ElectricViolet.copy(alpha = 0.35f), RoundedCornerShape(50))
        )
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.offset(y = floatY.dp)
        ) {
            Box(
                Modifier
                    .width(108.dp)
                    .height(132.dp)
                    .shadow(18.dp, RoundedCornerShape(8.dp))
                    .clip(RoundedCornerShape(8.dp))
                    .background(Brush.linearGradient(listOf(Color(0xFFFFFFFF), Color(0xFFDCE7F0))))
            ) {
                Box(
                    Modifier
                        .padding(start = 12.dp, top = 12.dp)
                        .size(14.dp)
                        .border(3.dp, Ink, RoundedCornerShape(2.dp))
                )
                Box(
                    Modifier
                        .align(Alignment.TopEnd)
                        .padding(top = 14.dp, end = 12.dp)
                        .width(46.dp)
                        .height(4.dp)
                        .clip(CircleShape)
                        .background(Color(0xFF0F766E))
                )
                Column(
                    Modifier.align(Alignment.BottomCenter).padding(bottom = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(7.dp)
                ) {
                    repeat(4) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            repeat(4) {
                                Box(Modifier.size(6.dp).border(1.dp, InkHigh, CircleShape))
                            }
                        }
                    }
                }
                Box(
                    Modifier
                        .fillMaxWidth()
                        .height(3.dp)
                        .offset(y = (18 + beam * 96).dp)
                        .background(Color(0xFF2DD4BF))
                        .shadow(12.dp, RoundedCornerShape(2.dp), ambientColor = Accent, spotColor = ElectricBlue)
                )
            }
            Box(
                Modifier
                    .width(168.dp)
                    .height(46.dp)
                    .offset(y = (-10).dp)
                    .shadow(16.dp, RoundedCornerShape(14.dp))
                    .clip(RoundedCornerShape(14.dp))
                    .background(Brush.linearGradient(listOf(Color(0xFF263854), InkLift)))
                    .border(1.dp, Color.White.copy(alpha = 0.08f), RoundedCornerShape(14.dp))
            ) {
                Row(
                    Modifier.fillMaxSize().padding(horizontal = 14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                        Box(Modifier.size(6.dp).clip(CircleShape).background(InkHigh))
                        Box(Modifier.size(6.dp).clip(CircleShape).background(InkHigh))
                        Box(Modifier.size(6.dp).clip(CircleShape).background(Accent).shadow(6.dp, CircleShape))
                    }
                    Text("OMR", color = Mute, fontSize = 9.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.4.sp)
                    Box(
                        Modifier
                            .width(22.dp)
                            .height(4.dp)
                            .clip(CircleShape)
                            .background(Accent)
                    )
                }
            }
        }
    }
}

@Composable
private fun HeroMetric(value: String, label: String) {
    Row(
        Modifier
            .clip(RoundedCornerShape(9.dp))
            .background(Color.White.copy(alpha = 0.04f))
            .border(1.dp, Color.White.copy(alpha = 0.07f), RoundedCornerShape(9.dp))
            .padding(horizontal = 8.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(value, color = Paper, fontSize = 11.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.width(5.dp))
        Text(label, color = Mute, fontSize = 8.sp, letterSpacing = .6.sp)
    }
}

@Composable
private fun SectionLabel(text: String, number: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(number, color = Accent, fontSize = 9.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
        Spacer(Modifier.width(8.dp))
        Text(text.uppercase(), color = Paper, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.25.sp)
    }
}

@Composable
private fun Chip(text: String, selected: Boolean, onClick: () -> Unit) {
    val bg by animateColorAsState(if (selected) Accent else InkLift, tween(160), label = "chip")
    val fg by animateColorAsState(if (selected) Ink else Paper, tween(160), label = "chipFg")
    Box(
        Modifier
            .shadow(if (selected) 10.dp else 2.dp, RoundedCornerShape(20.dp))
            .clip(RoundedCornerShape(20.dp))
            .background(bg)
            .border(1.dp, if (selected) Accent else Line, RoundedCornerShape(20.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 15.dp, vertical = 9.dp)
    ) {
        Text(text, color = fg, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun CursoRow(
    title: String,
    count: Int,
    selected: Boolean,
    iconMath: Boolean,
    onClick: () -> Unit
) {
    Row(
        Modifier
            .fillMaxWidth()
            .height(72.dp)
            .proPanel(
                radius = 18.dp,
                elevation = if (selected) 14.dp else 6.dp,
                borderColor = if (selected) Accent.copy(alpha = .75f) else Line
            )
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            Modifier
                .size(40.dp)
                .clip(RoundedCornerShape(12.dp))
                .background(if (selected) Accent.copy(alpha = .16f) else InkHigh),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                if (iconMath) Icons.Outlined.Functions else Icons.Outlined.AutoStories,
                contentDescription = null,
                tint = if (selected) Accent else ElectricBlue,
                modifier = Modifier.size(18.dp)
            )
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(title, color = Paper, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, maxLines = 1)
            Text(
                if (count == 0) "lote vacío" else "$count fichas guardadas",
                color = Mute,
                fontSize = 11.sp,
                modifier = Modifier.padding(top = 2.dp)
            )
        }
        Text(
            "$count",
            color = if (selected) Accent else Mute,
            fontWeight = FontWeight.Bold,
            fontSize = 16.sp
        )
    }
}

@Composable
private fun PrimaryButton(text: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Row(
        modifier
            .fillMaxWidth()
            .height(56.dp)
            .shadow(17.dp, RoundedCornerShape(17.dp), ambientColor = Accent.copy(alpha = .3f))
            .clip(RoundedCornerShape(17.dp))
            .background(AccentGradient)
            .clickable(onClick = onClick),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center
    ) {
        Icon(Icons.Outlined.CameraAlt, contentDescription = null, tint = Ink, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(9.dp))
        Text(text, color = Ink, fontWeight = FontWeight.Bold, fontSize = 14.sp)
    }
}

@Composable
private fun SecondaryButton(text: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Box(
        modifier
            .height(56.dp)
            .proPanel(radius = 17.dp, elevation = 8.dp)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center
    ) {
        Text(text, color = Paper, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
    }
}

@Composable
private fun LotRow(lot: Lot, onOpen: () -> Unit, onExport: () -> Unit, onDelete: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .proPanel(radius = 18.dp, elevation = 8.dp)
            .clickable(onClick = onOpen)
            .padding(horizontal = 15.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            Modifier
                .size(42.dp)
                .clip(RoundedCornerShape(13.dp))
                .background(Brush.linearGradient(listOf(Accent.copy(alpha = .2f), ElectricBlue.copy(alpha = .1f))))
                .border(1.dp, Accent.copy(alpha = .22f), RoundedCornerShape(13.dp)),
            contentAlignment = Alignment.Center
        ) {
            Text(lot.salon.takeLast(1), color = Accent, fontWeight = FontWeight.Bold, fontSize = 16.sp)
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text("${lot.salon} · ${lot.title}", color = Paper, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
            Text("${lot.photoCount} fichas listas", color = Mute, fontSize = 11.sp, modifier = Modifier.padding(top = 2.dp))
        }
        CircleAction(Icons.Outlined.IosShare, "Exportar", Accent, onExport)
        Spacer(Modifier.width(5.dp))
        CircleAction(Icons.Outlined.Delete, "Eliminar", Mute, onDelete)
        Icon(Icons.Outlined.ChevronRight, contentDescription = null, tint = Mute, modifier = Modifier.size(19.dp))
    }
}

@Composable
private fun CircleAction(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, tint: Color, onClick: () -> Unit) {
    Box(
        Modifier
            .size(38.dp)
            .clip(CircleShape)
            .background(InkHigh)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center
    ) {
        Icon(icon, contentDescription = label, tint = tint, modifier = Modifier.size(17.dp))
    }
}
