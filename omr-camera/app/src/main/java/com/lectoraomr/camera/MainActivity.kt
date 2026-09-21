package com.lectoraomr.camera

import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.lectoraomr.camera.data.ExportMode
import com.lectoraomr.camera.data.Lot
import com.lectoraomr.camera.data.ZipExporter
import com.lectoraomr.camera.ui.CameraScreen
import com.lectoraomr.camera.ui.HomeScreen
import com.lectoraomr.camera.ui.LotScreen
import com.lectoraomr.camera.ui.PackExportDialog
import com.lectoraomr.camera.ui.theme.Ink
import com.lectoraomr.camera.ui.theme.LectoraTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            LectoraTheme {
                OmrNav()
            }
        }
    }
}

@Composable
private fun OmrNav(vm: LotsViewModel = viewModel()) {
    val nav = rememberNavController()
    val ctx = LocalContext.current
    val lastUri by vm.lastExportUri.collectAsStateWithLifecycle()
    val lastName by vm.lastExportName.collectAsStateWithLifecycle()
    var lotExport by remember { mutableStateOf<Lot?>(null) }

    val fade = 120
    NavHost(
        navController = nav,
        startDestination = "home",
        modifier = Modifier
            .fillMaxSize()
            .background(Ink),
        enterTransition = { fadeIn(tween(fade)) + slideInHorizontally(tween(fade)) { it / 18 } },
        exitTransition = { fadeOut(tween(90)) },
        popEnterTransition = { fadeIn(tween(100)) },
        popExitTransition = { fadeOut(tween(90)) + slideOutHorizontally(tween(110)) { it / 18 } }
    ) {
        composable("home") {
            HomeScreen(
                vm = vm,
                onScan = { salon, curso ->
                    nav.navigate("camera/${enc(salon)}/${enc(curso)}")
                },
                onOpenLot = { lot ->
                    nav.navigate("lot/${enc(lot.salon)}/${enc(lot.curso)}")
                },
                onShareLast = lastUri?.let { uri ->
                    { ZipExporter.shareUri(ctx, uri, lastName) }
                },
                onOpenSelected = {
                    nav.navigate("lot/${enc(vm.salon.value)}/${enc(vm.curso.value)}")
                }
            )
        }
        composable(
            "camera/{salon}/{curso}?replace={replace}",
            arguments = listOf(
                navArgument("salon") { type = NavType.StringType },
                navArgument("curso") { type = NavType.StringType },
                navArgument("replace") {
                    type = NavType.StringType
                    defaultValue = ""
                    nullable = true
                }
            )
        ) { entry ->
            val salon = entry.arguments?.getString("salon").orEmpty()
            val curso = entry.arguments?.getString("curso").orEmpty()
            val replace = entry.arguments?.getString("replace").orEmpty()
            CameraScreen(
                salon = salon,
                curso = curso,
                repo = vm.repo,
                replacePath = replace.ifBlank { null },
                onBack = {
                    vm.refresh()
                    nav.popBackStack()
                }
            )
        }
        composable(
            "lot/{salon}/{curso}",
            arguments = listOf(
                navArgument("salon") { type = NavType.StringType },
                navArgument("curso") { type = NavType.StringType }
            )
        ) { entry ->
            val salon = entry.arguments?.getString("salon").orEmpty()
            val curso = entry.arguments?.getString("curso").orEmpty()
            LotScreen(
                salon = salon,
                curso = curso,
                repo = vm.repo,
                onBack = {
                    vm.refresh()
                    nav.popBackStack()
                },
                onScan = { nav.navigate("camera/${enc(salon)}/${enc(curso)}") },
                onExport = {
                    lotExport = Lot(salon, curso, vm.repo.count(salon, curso), vm.repo.lotDir(salon, curso))
                },
                onDeleteLot = {
                    vm.deleteLot(salon, curso)
                    vm.refresh()
                    nav.popBackStack()
                },
                onRetake = { file ->
                    nav.navigate("camera/${enc(salon)}/${enc(curso)}?replace=${enc(file.absolutePath)}")
                }
            )
        }
    }

    lotExport?.let { lot ->
        PackExportDialog(
            title = "Exportar lote",
            onDismiss = { lotExport = null },
            onConfirm = { name, mode ->
                val target = lot
                lotExport = null
                vm.exportPack(listOf(target), name, mode) { result ->
                    val msg = if (result.ok) {
                        if (mode == ExportMode.ZIP) "ZIP: ${result.name}" else "Carpetas: ${result.name}"
                    } else "No hay fotos"
                    Toast.makeText(ctx, msg, Toast.LENGTH_SHORT).show()
                }
            }
        )
    }
}

private fun enc(s: String): String = Uri.encode(s)
