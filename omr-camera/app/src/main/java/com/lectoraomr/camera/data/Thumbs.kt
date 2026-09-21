package com.lectoraomr.camera.data

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.LruCache
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import java.io.File

object Thumbs {
    private val cache = LruCache<String, Bitmap>(48)

    fun load(file: File, maxSide: Int = 240): ImageBitmap? {
        val bmp = decode(file, maxSide) ?: return null
        return bmp.asImageBitmap()
    }

    fun decode(file: File, maxSide: Int): Bitmap? {
        if (!file.exists()) return null
        val key = "${file.absolutePath}:${file.length()}:${file.lastModified()}:$maxSide"
        cache.get(key)?.let { return it }
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.absolutePath, bounds)
        val opts = BitmapFactory.Options().apply {
            inSampleSize = sample(bounds.outWidth, bounds.outHeight, maxSide)
            inPreferredConfig = Bitmap.Config.RGB_565
        }
        val bmp = BitmapFactory.decodeFile(file.absolutePath, opts) ?: return null
        cache.put(key, bmp)
        return bmp
    }

    private fun sample(w: Int, h: Int, maxSide: Int): Int {
        if (w <= 0 || h <= 0) return 1
        var s = 1
        while (w / s > maxSide * 2 || h / s > maxSide * 2) s *= 2
        return s
    }
}
