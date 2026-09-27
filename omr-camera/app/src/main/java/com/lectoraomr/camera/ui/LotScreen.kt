package com.lectoraomr.camera.ui

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ArrowBack
import androidx.compose.material.icons.outlined.CameraAlt
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.IosShare
import androidx.compose.material.icons.outlined.PhotoLibrary
import androidx.compose.material.icons.outlined.Replay
import androidx.compose.material3.Icon
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
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.runtime.produceState
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.lectoraomr.camera.data.Catalog
import com.lectoraomr.camera.data.LotRepository
import com.lectoraomr.camera.data.Thumbs
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import com.lectoraomr.camera.ui.theme.Accent
import com.lectoraomr.camera.ui.theme.AccentGradient
import com.lectoraomr.camera.ui.theme.AppBackdrop
import com.lectoraomr.camera.ui.theme.Danger
import com.lectoraomr.camera.ui.theme.ElectricBlue
import com.lectoraomr.camera.ui.theme.Ink
import com.lectoraomr.camera.ui.theme.InkHigh
import com.lectoraomr.camera.ui.theme.InkLift
import com.lectoraomr.camera.ui.theme.Mute
import com.lectoraomr.camera.ui.theme.Paper
import com.lectoraomr.camera.ui.theme.Line
import com.lectoraomr.camera.ui.theme.proPanel
import java.io.File

@Composable
fun LotScreen(
    salon: String,
    curso: String,
    repo: LotRepository,
    onBack: () -> Unit,
    onScan: () -> Unit,
    onExport: () -> Unit,
    onDeleteLot: () -> Unit,
    onRetake: (File) -> Unit
) {
    val context = LocalContext.current
    var photos by remember { mutableStateOf(repo.photos(salon, curso)) }
    var viewing by remember { mutableStateOf<File?>(null) }
    var confirmDelete by remember { mutableStateOf<File?>(null) }
    var confirmDeleteLot by remember { mutableStateOf(false) }
    var showReplace by remember { mutableStateOf(false) }

    fun reload() {
        photos = repo.photos(salon, curso)
        val still = viewing?.let { v -> photos.firstOrNull { it.absolutePath == v.absolutePath } }
        viewing = still
    }
    LaunchedEffect(salon, curso) { reload() }

    val gallery = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
        val target = viewing ?: return@rememberLauncherForActivityResult
        if (uri == null) return@rememberLauncherForActivityResult
        context.contentResolver.openInputStream(uri)?.use { input ->
            repo.replacePhotoFromStream(target, input)
        }
        showReplace = false
        reload()
    }

    AppBackdrop(Modifier.fillMaxSize()) {
        Column(
            Modifier
                .fillMaxSize()
                .statusBarsPadding()
                .navigationBarsPadding()
        ) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 8.dp)
                    .proPanel(radius = 18.dp, elevation = 10.dp)
                    .padding(horizontal = 4.dp, vertical = 5.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    Icons.Outlined.ArrowBack,
                    contentDescription = "Volver",
                    tint = Paper,
                    modifier = Modifier
                        .size(40.dp)
                        .clip(RoundedCornerShape(12.dp))
                        .clickable(onClick = onBack)
                        .padding(8.dp)
                )
                Column(Modifier.weight(1f).padding(start = 4.dp)) {
                    Text("LOTE · $salon", color = Accent, fontSize = 9.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.1.sp)
                    Text(Catalog.cursoLabel(curso), color = Paper, fontWeight = FontWeight.SemiBold, fontSize = 20.sp)
                }
                Text("${photos.size}", color = Accent, fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                Text(" fichas", color = Mute, fontSize = 13.sp, modifier = Modifier.padding(end = 10.dp))
            }

            if (photos.isEmpty()) {
                Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                    Column(
                        Modifier.padding(28.dp).proPanel(radius = 20.dp, elevation = 10.dp).padding(26.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Box(
                            Modifier.size(52.dp).clip(RoundedCornerShape(16.dp))
                                .background(Accent.copy(alpha = .12f)),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(Icons.Outlined.PhotoLibrary, null, tint = Accent, modifier = Modifier.size(24.dp))
                        }
                        Spacer(Modifier.height(12.dp))
                        Text("Sin fotos en este lote", color = Paper, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
                        Spacer(Modifier.height(6.dp))
                        Text("Escanea fichas o importa desde galería.", color = Mute.copy(alpha = 0.75f), fontSize = 13.sp)
                    }
                }
            } else {
                LazyVerticalGrid(
                    columns = GridCells.Fixed(3),
                    contentPadding = PaddingValues(start = 14.dp, end = 14.dp, bottom = 12.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.weight(1f)
                ) {
                    items(photos, key = { it.absolutePath }) { file ->
                        PhotoCell(file) { viewing = file }
                    }
                }
            }

            Row(
                Modifier
                    .fillMaxWidth()
                    .background(Brush.verticalGradient(listOf(Color.Transparent, Ink.copy(alpha = .92f))))
                    .padding(horizontal = 16.dp, vertical = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                ActionPill("Escanear", Accent, Ink, Icons.Outlined.CameraAlt, Modifier.weight(1.35f), onScan)
                ActionPill("Exportar", InkHigh, Paper, Icons.Outlined.IosShare, Modifier.weight(1f), onExport)
                ActionPill("Borrar", Danger.copy(alpha = 0.18f), Danger, Icons.Outlined.Delete, Modifier.weight(1f), { confirmDeleteLot = true })
            }
            CreditsFooter(Modifier.padding(horizontal = 16.dp))
        }

        AnimatedVisibility(
            visible = viewing != null,
            enter = fadeIn(),
            exit = fadeOut()
        ) {
            val file = viewing
            if (file != null) {
                PhotoViewer(
                    file = file,
                    onClose = { viewing = null; showReplace = false },
                    onDelete = { confirmDelete = file },
                    onReplaceMenu = { showReplace = true },
                    showReplace = showReplace,
                    onRetake = {
                        showReplace = false
                        viewing = null
                        onRetake(file)
                    },
                    onGallery = { gallery.launch("image/*") }
                )
            }
        }

        confirmDelete?.let { file ->
            ConfirmDialog(
                title = "Eliminar ficha",
                body = "Se quitará ${file.nameWithoutExtension} de este lote.",
                confirm = "Eliminar",
                danger = true,
                onConfirm = {
                    repo.deletePhoto(file)
                    confirmDelete = null
                    viewing = null
                    showReplace = false
                    reload()
                },
                onDismiss = { confirmDelete = null }
            )
        }
        if (confirmDeleteLot) {
            ConfirmDialog(
                title = "Eliminar lote",
                body = "Se borrarán ${photos.size} fichas de $salon · ${Catalog.cursoLabel(curso)}.",
                confirm = "Eliminar",
                danger = true,
                onConfirm = {
                    confirmDeleteLot = false
                    onDeleteLot()
                },
                onDismiss = { confirmDeleteLot = false }
            )
        }
    }
}

@Composable
private fun ActionPill(
    text: String,
    bg: Color,
    fg: Color,
    icon: ImageVector,
    modifier: Modifier,
    onClick: () -> Unit
) {
    Row(
        modifier
            .height(48.dp)
            .shadow(10.dp, RoundedCornerShape(14.dp))
            .clip(RoundedCornerShape(14.dp))
            .background(bg)
            .border(1.dp, fg.copy(alpha = .18f), RoundedCornerShape(14.dp))
            .clickable(onClick = onClick),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center
    ) {
        Icon(icon, contentDescription = null, tint = fg, modifier = Modifier.size(18.dp))
        Spacer(Modifier.size(8.dp))
        Text(text, color = fg, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
    }
}

@Composable
private fun PhotoCell(file: File, onOpen: () -> Unit) {
    val bmp by produceState<ImageBitmap?>(null, file.path, file.length(), file.lastModified()) {
        value = withContext(Dispatchers.IO) { Thumbs.load(file, 240) }
    }
    Box(
        Modifier
            .aspectRatio(148f / 210f)
            .shadow(13.dp, RoundedCornerShape(13.dp))
            .clip(RoundedCornerShape(10.dp))
            .background(InkLift)
            .border(1.dp, Line.copy(alpha = .85f), RoundedCornerShape(10.dp))
            .clickable(onClick = onOpen)
    ) {
        val shown = bmp
        if (shown != null) {
            Image(shown, contentDescription = file.name, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
        }
        Text(
            file.nameWithoutExtension.take(3),
            color = Paper,
            fontSize = 10.sp,
            fontWeight = FontWeight.Medium,
            modifier = Modifier
                .align(Alignment.BottomStart)
                .clip(RoundedCornerShape(6.dp))
                .background(Ink.copy(alpha = .72f))
                .padding(horizontal = 6.dp, vertical = 4.dp)
        )
    }
}

@Composable
private fun PhotoViewer(
    file: File,
    onClose: () -> Unit,
    onDelete: () -> Unit,
    onReplaceMenu: () -> Unit,
    showReplace: Boolean,
    onRetake: () -> Unit,
    onGallery: () -> Unit
) {
    val bmp by produceState<ImageBitmap?>(null, file.path, file.length(), file.lastModified()) {
        value = withContext(Dispatchers.IO) { Thumbs.load(file, 1280) }
    }
    Column(
        Modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(Ink.copy(alpha = .97f), Color(0xFF081426))))
            .statusBarsPadding()
            .navigationBarsPadding()
    ) {
        Row(
            Modifier.fillMaxWidth().padding(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                Icons.Outlined.Close,
                contentDescription = "Cerrar",
                tint = Paper,
                modifier = Modifier
                    .size(40.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .clickable(onClick = onClose)
                    .padding(8.dp)
            )
            Text(
                file.nameWithoutExtension,
                color = Paper,
                fontWeight = FontWeight.Medium,
                fontSize = 14.sp,
                modifier = Modifier.weight(1f).padding(start = 4.dp)
            )
        }
        Box(
            Modifier
                .weight(1f)
                .fillMaxWidth()
                .padding(horizontal = 12.dp)
                .clip(RoundedCornerShape(12.dp))
                .background(InkLift),
            contentAlignment = Alignment.Center
        ) {
            val shown = bmp
            if (shown != null) {
                Image(shown, contentDescription = file.name, contentScale = ContentScale.Fit, modifier = Modifier.fillMaxSize())
            }
        }
        if (showReplace) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 10.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                ActionPill("Cámara", Accent, Ink, Icons.Outlined.CameraAlt, Modifier.weight(1f), onRetake)
                ActionPill("Galería", InkHigh, Paper, Icons.Outlined.PhotoLibrary, Modifier.weight(1f), onGallery)
            }
        } else {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 10.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                ActionPill("Reemplazar", InkHigh, Paper, Icons.Outlined.Replay, Modifier.weight(1.2f), onReplaceMenu)
                ActionPill("Eliminar", Danger.copy(alpha = 0.18f), Danger, Icons.Outlined.Delete, Modifier.weight(1f), onDelete)
            }
        }
    }
}

