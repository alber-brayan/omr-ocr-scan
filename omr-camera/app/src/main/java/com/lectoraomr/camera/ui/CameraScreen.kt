package com.lectoraomr.camera.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.view.WindowManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ArrowBack
import androidx.compose.material.icons.outlined.FlashOff
import androidx.compose.material.icons.outlined.FlashOn
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import kotlinx.coroutines.delay
import android.os.SystemClock
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.lectoraomr.camera.camera.SheetAnalyzer
import com.lectoraomr.camera.camera.SheetQuality
import com.lectoraomr.camera.data.Catalog
import com.lectoraomr.camera.data.LotRepository
import com.lectoraomr.camera.ui.theme.Accent
import com.lectoraomr.camera.ui.theme.Danger
import com.lectoraomr.camera.ui.theme.Ink
import com.lectoraomr.camera.ui.theme.Mute
import com.lectoraomr.camera.ui.theme.Paper
import com.lectoraomr.camera.ui.theme.Warn
import java.util.concurrent.Executors

@Composable
fun CameraScreen(
    salon: String,
    curso: String,
    repo: LotRepository,
    onBack: () -> Unit,
    replacePath: String? = null
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    var granted by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED
        )
    }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        granted = it
    }
    LaunchedEffect(Unit) {
        if (!granted) launcher.launch(Manifest.permission.CAMERA)
    }

    DisposableEffect(Unit) {
        val win = (context as? android.app.Activity)?.window
        win?.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        onDispose { win?.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
    }

    if (!granted) {
        Box(
            Modifier
                .fillMaxSize()
                .background(Ink)
                .clickable { launcher.launch(Manifest.permission.CAMERA) },
            contentAlignment = Alignment.Center
        ) {
            Text("Toca para permitir la cámara", color = Paper)
        }
        return
    }

    var quality by remember { mutableStateOf(SheetQuality()) }
    var count by remember { mutableIntStateOf(repo.count(salon, curso)) }
    var torch by remember { mutableStateOf(false) }
    var capturing by remember { mutableStateOf(false) }
    var flashWhite by remember { mutableStateOf(false) }
    var armed by remember { mutableStateOf(true) }
    var cooldownUntil by remember { mutableLongStateOf(0L) }
    var nowTick by remember { mutableLongStateOf(0L) }
    var camera by remember { mutableStateOf<androidx.camera.core.Camera?>(null) }
    var previewView by remember { mutableStateOf<PreviewView?>(null) }
    val mainExecutor = remember { ContextCompat.getMainExecutor(context) }
    val analyzer = remember {
        SheetAnalyzer { q -> mainExecutor.execute { quality = q } }
    }
    val imageCapture = remember {
        ImageCapture.Builder()
            .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
            .setJpegQuality(90)
            .build()
    }
    val analysisExecutor = remember { Executors.newSingleThreadExecutor() }
    DisposableEffect(Unit) {
        onDispose { analysisExecutor.shutdown() }
    }
    val cooling = nowTick < cooldownUntil
    val remainMs = (cooldownUntil - nowTick).coerceAtLeast(0L)

    fun vibrate(ms: Long = 35) {
        val v = if (Build.VERSION.SDK_INT >= 31) {
            (context.getSystemService(VibratorManager::class.java)).defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            context.getSystemService(Vibrator::class.java)
        }
        v.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE))
    }

    val replacing = !replacePath.isNullOrBlank()
    fun shoot() {
        if (capturing) return
        capturing = true
        val file = if (replacing) java.io.File(replacePath!!) else repo.nextPhotoFile(salon, curso)
        val opts = ImageCapture.OutputFileOptions.Builder(file).build()
        imageCapture.takePicture(
            opts,
            ContextCompat.getMainExecutor(context),
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(outputFileResults: ImageCapture.OutputFileResults) {
                    count = repo.count(salon, curso)
                    capturing = false
                    armed = false
                    val until = SystemClock.elapsedRealtime() + 1500L
                    cooldownUntil = until
                    nowTick = SystemClock.elapsedRealtime()
                    flashWhite = true
                    vibrate(28)
                    if (replacing) onBack()
                }
                override fun onError(exception: ImageCaptureException) {
                    capturing = false
                }
            }
        )
    }

    LaunchedEffect(flashWhite) {
        if (flashWhite) {
            delay(90)
            flashWhite = false
        }
    }
    LaunchedEffect(cooldownUntil) {
        while (SystemClock.elapsedRealtime() < cooldownUntil) {
            nowTick = SystemClock.elapsedRealtime()
            delay(50)
        }
        nowTick = SystemClock.elapsedRealtime()
    }
    LaunchedEffect(capturing, cooling) {
        analyzer.paused = capturing || cooling
    }
    LaunchedEffect(quality.ready, cooling) {
        if (!cooling && !quality.ready) armed = true
    }
    LaunchedEffect(quality.ready, capturing, cooling, armed) {
        if (capturing || cooling || !armed || !quality.ready || replacing) return@LaunchedEffect
        delay(140)
        if (!capturing && !cooling && armed && quality.ready) shoot()
    }

    LaunchedEffect(previewView, lifecycleOwner) {
        val pv = previewView ?: return@LaunchedEffect
        val future = ProcessCameraProvider.getInstance(context)
        future.addListener({
            val provider = future.get()
            val preview = Preview.Builder().build().also {
                it.surfaceProvider = pv.surfaceProvider
            }
            val analysis = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_YUV_420_888)
                .build()
                .also { ia ->
                    ia.setAnalyzer(analysisExecutor, analyzer)
                }
            try {
                provider.unbindAll()
                camera = provider.bindToLifecycle(
                    lifecycleOwner,
                    CameraSelector.DEFAULT_BACK_CAMERA,
                    preview,
                    imageCapture,
                    analysis
                )
                camera?.cameraControl?.enableTorch(torch)
            } catch (_: Exception) {
            }
        }, mainExecutor)
    }

    Box(Modifier.fillMaxSize().background(Ink)) {
        AndroidView(
            modifier = Modifier.fillMaxSize(),
            factory = { ctx ->
                PreviewView(ctx).apply {
                    scaleType = PreviewView.ScaleType.FIT_CENTER
                    implementationMode = PreviewView.ImplementationMode.COMPATIBLE
                    previewView = this
                }
            }
        )

        SheetOverlay(quality, Modifier.fillMaxSize())

        if (flashWhite) {
            Box(Modifier.fillMaxSize().background(Color.White.copy(alpha = 0.35f)))
        }

        Column(
            Modifier
                .fillMaxWidth()
                .statusBarsPadding()
                .padding(horizontal = 16.dp, vertical = 8.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    Icons.Outlined.ArrowBack,
                    contentDescription = "Cerrar",
                    tint = Paper,
                    modifier = Modifier
                        .size(40.dp)
                        .clip(CircleShape)
                        .background(Ink.copy(alpha = 0.45f))
                        .clickable(onClick = onBack)
                        .padding(8.dp)
                )
                Spacer(Modifier.weight(1f))
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        "$salon  ·  ${Catalog.cursoLabel(curso)}",
                        color = Paper,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Medium
                    )
                    Text(
                        if (replacing) "Reemplazar ficha" else "$count fichas",
                        color = Mute,
                        fontSize = 11.sp
                    )
                }
                Spacer(Modifier.weight(1f))
                Icon(
                    if (torch) Icons.Outlined.FlashOn else Icons.Outlined.FlashOff,
                    contentDescription = "Linterna",
                    tint = if (torch) Warn else Paper,
                    modifier = Modifier
                        .size(40.dp)
                        .clip(CircleShape)
                        .background(Ink.copy(alpha = 0.45f))
                        .clickable {
                            torch = !torch
                            camera?.cameraControl?.enableTorch(torch)
                        }
                        .padding(8.dp)
                )
            }
        }

        Column(
            Modifier
                .align(Alignment.BottomCenter)
                .navigationBarsPadding()
                .padding(bottom = 22.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            val coolingNow = cooling
            val pillColor = when {
                coolingNow -> Warn
                capturing -> Warn
                quality.level == SheetQuality.Level.Go -> Accent
                quality.level == SheetQuality.Level.Almost -> Warn
                else -> Danger
            }
            val hintText = when {
                capturing -> "Guardando…"
                coolingNow -> "Cambia la ficha  ·  ${"%.1f".format(remainMs / 1000f)}s"
                !armed -> "Retira la ficha para la siguiente"
                quality.ready -> "4 guías · disparo automático"
                else -> quality.hint
            }
            Box(
                Modifier
                    .clip(RoundedCornerShape(24.dp))
                    .background(Ink.copy(alpha = 0.72f))
                    .padding(horizontal = 16.dp, vertical = 8.dp)
            ) {
                Text(
                    hintText,
                    color = pillColor,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Medium
                )
            }
            Spacer(Modifier.height(18.dp))
            Box(contentAlignment = Alignment.Center) {
                Box(
                    Modifier
                        .size(84.dp)
                        .clip(CircleShape)
                        .border(3.dp, if (quality.ready) Accent else Paper.copy(alpha = 0.55f), CircleShape)
                )
                Box(
                    Modifier
                        .size(68.dp)
                        .clip(CircleShape)
                        .background(if (quality.ready) Accent else Paper)
                        .clickable(enabled = !capturing) { shoot() }
                )
            }
            Spacer(Modifier.height(10.dp))
            Text(
                when {
                    coolingNow -> "Pausa 1.5 s para no repetir la foto"
                    quality.ready && armed -> "Disparo automático"
                    else -> "4 guías → dispara solo  ·  o toca el botón"
                },
                color = Mute,
                fontSize = 11.sp
            )
        }
    }
}
