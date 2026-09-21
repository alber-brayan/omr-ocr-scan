package com.lectoraomr.camera.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
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
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.lectoraomr.camera.data.ExportMode
import com.lectoraomr.camera.data.ZipExporter
import com.lectoraomr.camera.ui.theme.Accent
import com.lectoraomr.camera.ui.theme.Danger
import com.lectoraomr.camera.ui.theme.Ink
import com.lectoraomr.camera.ui.theme.InkHigh
import com.lectoraomr.camera.ui.theme.InkLift
import com.lectoraomr.camera.ui.theme.Mute
import com.lectoraomr.camera.ui.theme.Paper

@Composable
fun PackExportDialog(
    title: String,
    defaultName: String = ZipExporter.defaultPackName(),
    onDismiss: () -> Unit,
    onConfirm: (String, ExportMode) -> Unit
) {
    var name by remember { mutableStateOf(defaultName) }
    var mode by remember { mutableStateOf(ExportMode.ZIP) }
    Dialog(onDismissRequest = onDismiss) {
        Column(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(20.dp))
                .background(InkLift)
                .padding(22.dp)
        ) {
            Text(title, color = Paper, fontWeight = FontWeight.SemiBold, fontSize = 18.sp)
            Spacer(Modifier.height(6.dp))
            Text(
                "Se guarda en ${ZipExporter.FOLDER_LABEL}/nombre",
                color = Mute,
                fontSize = 13.sp
            )
            Spacer(Modifier.height(16.dp))
            Text("NOMBRE DE LA CARPETA", color = Mute, fontSize = 11.sp, letterSpacing = 1.2.sp, fontWeight = FontWeight.Medium)
            Spacer(Modifier.height(8.dp))
            Box(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(InkHigh)
                    .border(1.dp, Accent.copy(alpha = 0.25f), RoundedCornerShape(12.dp))
                    .padding(horizontal = 14.dp, vertical = 12.dp)
            ) {
                BasicTextField(
                    value = name,
                    onValueChange = { name = it },
                    singleLine = true,
                    textStyle = TextStyle(color = Paper, fontSize = 15.sp),
                    cursorBrush = SolidColor(Accent),
                    modifier = Modifier.fillMaxWidth()
                )
            }
            Spacer(Modifier.height(16.dp))
            Text("FORMATO", color = Mute, fontSize = 11.sp, letterSpacing = 1.2.sp, fontWeight = FontWeight.Medium)
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ModeChip("ZIP", mode == ExportMode.ZIP) { mode = ExportMode.ZIP }
                ModeChip("Carpetas", mode == ExportMode.FOLDERS) { mode = ExportMode.FOLDERS }
            }
            Spacer(Modifier.height(8.dp))
            Text(
                if (mode == ExportMode.ZIP)
                    "Incluye manifest.json para calificar todos los salones de un clic en el servidor."
                else
                    "Crea Descargas/LectoraOMR/nombre/Sección/Curso/ con el manifiesto.",
                color = Mute,
                fontSize = 12.sp,
                lineHeight = 17.sp
            )
            Spacer(Modifier.height(20.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Box(
                    Modifier
                        .weight(1f)
                        .height(46.dp)
                        .clip(RoundedCornerShape(12.dp))
                        .background(InkHigh)
                        .clickable(onClick = onDismiss),
                    contentAlignment = Alignment.Center
                ) {
                    Text("Cancelar", color = Mute, fontWeight = FontWeight.Medium)
                }
                Box(
                    Modifier
                        .weight(1f)
                        .height(46.dp)
                        .clip(RoundedCornerShape(12.dp))
                        .background(Accent)
                        .clickable { onConfirm(name.trim(), mode) },
                    contentAlignment = Alignment.Center
                ) {
                    Text("Guardar", color = Ink, fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

@Composable
private fun ModeChip(label: String, selected: Boolean, onClick: () -> Unit) {
    Box(
        Modifier
            .clip(RoundedCornerShape(20.dp))
            .background(if (selected) Accent else InkHigh)
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 8.dp)
    ) {
        Text(label, color = if (selected) Ink else Paper, fontSize = 13.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
fun ConfirmDialog(
    title: String,
    body: String,
    confirm: String,
    danger: Boolean = false,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit
) {
    Box(
        Modifier
            .fillMaxSize()
            .background(Color.Black.copy(alpha = 0.45f))
            .clickable(onClick = onDismiss),
        contentAlignment = Alignment.Center
    ) {
        Column(
            Modifier
                .padding(28.dp)
                .clip(RoundedCornerShape(18.dp))
                .background(InkLift)
                .clickable(enabled = false, onClick = {})
                .padding(20.dp)
        ) {
            Text(title, color = Paper, fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
            Spacer(Modifier.height(8.dp))
            Text(body, color = Mute, fontSize = 14.sp, lineHeight = 20.sp)
            Spacer(Modifier.height(18.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Box(
                    Modifier
                        .weight(1f)
                        .height(44.dp)
                        .clip(RoundedCornerShape(12.dp))
                        .background(InkHigh)
                        .clickable(onClick = onDismiss),
                    contentAlignment = Alignment.Center
                ) { Text("Cancelar", color = Mute, fontWeight = FontWeight.Medium) }
                Box(
                    Modifier
                        .weight(1f)
                        .height(44.dp)
                        .clip(RoundedCornerShape(12.dp))
                        .background(if (danger) Danger else Accent)
                        .clickable(onClick = onConfirm),
                    contentAlignment = Alignment.Center
                ) { Text(confirm, color = if (danger) Paper else Ink, fontWeight = FontWeight.SemiBold) }
            }
        }
    }
}
