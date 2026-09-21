package com.lectoraomr.camera.data

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.core.content.FileProvider
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.File
import java.io.FileInputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

data class ExportResult(
    val ok: Boolean,
    val name: String,
    val folderLabel: String,
    val uri: Uri?,
    val mode: ExportMode = ExportMode.ZIP
)

enum class ExportMode { ZIP, FOLDERS }

object ZipExporter {
    const val FOLDER_LABEL = "Descargas / LectoraOMR"

    fun defaultPackName(): String =
        "OMR_${SimpleDateFormat("yyyyMMdd", Locale.US).format(Date())}"

    fun exportPack(
        context: Context,
        repo: LotRepository,
        lots: List<Lot>,
        packName: String,
        mode: ExportMode
    ): ExportResult {
        if (lots.isEmpty()) return ExportResult(false, "", FOLDER_LABEL, null, mode)
        val base = sanitizeFileName(packName.removeSuffix(".zip").ifBlank { defaultPackName() })
        val entries = mutableListOf<Pair<String, File>>()
        val lotMeta = JSONArray()
        for (lot in lots) {
            val photos = repo.photos(lot.salon, lot.curso)
            if (photos.isEmpty()) continue
            val prefix = "${Catalog.safeName(lot.salon)}/${Catalog.safeName(lot.curso)}"
            for (f in photos) entries += "$prefix/${f.name}" to f
            lotMeta.put(
                JSONObject()
                    .put("salon", lot.salon)
                    .put("curso", lot.curso)
                    .put("folder", prefix)
                    .put("count", photos.size)
            )
        }
        if (entries.isEmpty()) return ExportResult(false, "", FOLDER_LABEL, null, mode)
        val manifest = JSONObject()
            .put("format", "lectoraomr-pack")
            .put("version", 1)
            .put("name", base)
            .put("created", isoStamp())
            .put("lots", lotMeta)
            .toString(2)

        return if (mode == ExportMode.FOLDERS) {
            writeFolders(context, base, entries, manifest)
        } else {
            saveZip(context, base, entries, manifest)
        }
    }

    fun shareUri(context: Context, uri: Uri, name: String) {
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "application/zip"
            putExtra(Intent.EXTRA_STREAM, uri)
            putExtra(Intent.EXTRA_SUBJECT, name)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            clipData = android.content.ClipData.newRawUri(name, uri)
        }
        context.startActivity(Intent.createChooser(intent, "Enviar ZIP OMR"))
    }

    private fun saveZip(
        context: Context,
        base: String,
        entries: List<Pair<String, File>>,
        manifest: String
    ): ExportResult {
        val tmp = buildZip(context, "$base.zip", entries, manifest)
        val uri = writeToDownloads(context, tmp, "$base.zip", "application/zip", "")
        tmp.delete()
        return ExportResult(uri != null, "$base.zip", FOLDER_LABEL, uri, ExportMode.ZIP)
    }

    private fun writeFolders(
        context: Context,
        base: String,
        entries: List<Pair<String, File>>,
        manifest: String
    ): ExportResult {
        var ok = writeTextToDownloads(context, manifest, "manifest.json", "$base")
        for ((rel, file) in entries) {
            val parent = rel.substringBeforeLast("/", "")
            val name = rel.substringAfterLast("/")
            val relPath = if (parent.isBlank()) base else "$base/$parent"
            if (!copyFileToDownloads(context, file, name, "image/jpeg", relPath)) ok = false
        }
        val uri = if (Build.VERSION.SDK_INT >= 29) null else {
            @Suppress("DEPRECATION")
            val dir = File(
                Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),
                "LectoraOMR/$base"
            )
            if (dir.exists()) FileProvider.getUriForFile(context, "${context.packageName}.files", dir) else null
        }
        return ExportResult(ok, base, "$FOLDER_LABEL/$base", uri, ExportMode.FOLDERS)
    }

    private fun writeToDownloads(
        context: Context,
        file: File,
        displayName: String,
        mime: String,
        subDir: String
    ): Uri? {
        val rel = Environment.DIRECTORY_DOWNLOADS + "/LectoraOMR" +
            if (subDir.isBlank()) "" else "/$subDir"
        return if (Build.VERSION.SDK_INT >= 29) {
            val resolver = context.contentResolver
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, displayName)
                put(MediaStore.Downloads.MIME_TYPE, mime)
                put(MediaStore.Downloads.RELATIVE_PATH, rel)
                put(MediaStore.Downloads.IS_PENDING, 1)
            }
            val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return null
            resolver.openOutputStream(uri)?.use { out ->
                file.inputStream().use { it.copyTo(out) }
            } ?: return null
            values.clear()
            values.put(MediaStore.Downloads.IS_PENDING, 0)
            resolver.update(uri, values, null, null)
            uri
        } else {
            @Suppress("DEPRECATION")
            val dir = File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "LectoraOMR" + if (subDir.isBlank()) "" else "/$subDir")
            if (!dir.exists()) dir.mkdirs()
            var dest = File(dir, displayName)
            if (dest.exists()) dest = File(dir, "${dest.nameWithoutExtension}_${stamp()}${dest.extension.let { if (it.isBlank()) "" else ".$it" }}")
            file.copyTo(dest, overwrite = true)
            FileProvider.getUriForFile(context, "${context.packageName}.files", dest)
        }
    }

    private fun copyFileToDownloads(
        context: Context,
        file: File,
        displayName: String,
        mime: String,
        subDir: String
    ): Boolean {
        return if (Build.VERSION.SDK_INT >= 29) {
            writeToDownloads(context, file, displayName, mime, subDir) != null
        } else {
            @Suppress("DEPRECATION")
            val dir = File(
                Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),
                "LectoraOMR/$subDir"
            )
            if (!dir.exists()) dir.mkdirs()
            file.copyTo(File(dir, displayName), overwrite = true)
            true
        }
    }

    private fun writeTextToDownloads(
        context: Context,
        text: String,
        displayName: String,
        subDir: String
    ): Boolean {
        val tmp = File(context.cacheDir, displayName)
        tmp.writeText(text, Charsets.UTF_8)
        val ok = writeToDownloads(context, tmp, displayName, "application/json", subDir) != null
        tmp.delete()
        return ok
    }

    private fun buildZip(
        context: Context,
        name: String,
        entries: List<Pair<String, File>>,
        manifest: String
    ): File {
        val dir = File(context.cacheDir, "zips").apply { mkdirs() }
        val zip = File(dir, name)
        if (zip.exists()) zip.delete()
        ZipOutputStream(zip.outputStream().buffered()).use { zos ->
            zos.putNextEntry(ZipEntry("manifest.json"))
            zos.write(manifest.toByteArray(Charsets.UTF_8))
            zos.closeEntry()
            val buf = ByteArray(64 * 1024)
            for ((path, file) in entries) {
                zos.putNextEntry(ZipEntry(path.replace("\\", "/")))
                BufferedInputStream(FileInputStream(file)).use { input ->
                    while (true) {
                        val n = input.read(buf)
                        if (n <= 0) break
                        zos.write(buf, 0, n)
                    }
                }
                zos.closeEntry()
            }
        }
        return zip
    }

    private fun stamp(): String = SimpleDateFormat("yyyyMMdd_HHmm", Locale.US).format(Date())

    private fun isoStamp(): String = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US).format(Date())

    fun sanitizeFileName(raw: String): String =
        raw.trim().replace(Regex("""[\\/:*?"<>|]"""), "-").ifBlank { "OMR_lote" }
}
