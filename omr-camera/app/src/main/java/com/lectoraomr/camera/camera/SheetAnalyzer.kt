package com.lectoraomr.camera.camera

import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.sqrt

/**
 * Permissive quality gate aligned to the printed A5 sheet:
 *   markers inset 5 mm, size 10 mm → center at 10 mm
 *   = 10/148 of width, 10/210 of height.
 */
class SheetAnalyzer(
    private val onResult: (SheetQuality) -> Unit
) : ImageAnalysis.Analyzer {

    @Volatile
    var paused: Boolean = false

    @Volatile
    private var lastEmit = 0L

    override fun analyze(image: ImageProxy) {
        try {
            if (paused) return
            val gray = downscaleUpright(image, maxSide = 320) ?: return
            val q = evaluate(gray)
            val now = System.currentTimeMillis()
            if (now - lastEmit >= 55) {
                lastEmit = now
                onResult(q)
            }
        } finally {
            image.close()
        }
    }

    private fun evaluate(g: Gray): SheetQuality {
        val a5 = a5InImage(g.w, g.h, margin = 0.045f)
        val brightness = mean(g, a5) / 255f
        val fill = paperFill(g, a5)
        val sharpness = sharpnessScore(g, a5)

        val win = max(22, (a5.w * 0.22f).roundToInt())
        val corners = CornerHits(
            tl = hasMarker(g, markerWindow(a5, 0.0676f, 0.0476f, win)),
            tr = hasMarker(g, markerWindow(a5, 0.9324f, 0.0476f, win)),
            bl = hasMarker(g, markerWindow(a5, 0.0676f, 0.9524f, win)),
            br = hasMarker(g, markerWindow(a5, 0.9324f, 0.9524f, win))
        )

        val four = corners.count >= 4
        val threeOk = corners.count >= 3 && fill >= 0.22f && sharpness >= 0.10f
        val paperOk = fill >= 0.18f && brightness in 0.12f..0.97f && sharpness >= 0.08f
        val ready = paperOk && (four || threeOk)

        val hint = when {
            brightness < 0.12f -> "Muy oscuro — busca más luz"
            brightness > 0.97f -> "Hay destello — inclina un poco"
            fill < 0.18f -> "Acerca la ficha al recuadro"
            sharpness < 0.08f -> "Un poco borroso — sostén firme"
            four -> "4 guías · disparo automático"
            corners.count == 3 -> "3/4 guías — mantén un segundo"
            corners.count in 1..2 -> "Faltan guías (${corners.missing.first()})"
            else -> "Encaja la ficha A5"
        }

        return SheetQuality(
            sharpness = sharpness,
            brightness = brightness,
            fill = fill,
            corners = corners,
            hint = hint,
            ready = ready,
            imageAspect = g.w / g.h.toFloat()
        )
    }

    private fun a5InImage(w: Int, h: Int, margin: Float): RectI {
        val availW = w * (1f - 2f * margin)
        val availH = h * (1f - 2f * margin)
        val aspect = 148f / 210f
        val rw: Float
        val rh: Float
        if (availW / availH > aspect) {
            rh = availH
            rw = rh * aspect
        } else {
            rw = availW
            rh = rw / aspect
        }
        val l = ((w - rw) / 2f).roundToInt()
        val t = ((h - rh) / 2f).roundToInt()
        return RectI(l, t, l + rw.roundToInt(), t + rh.roundToInt())
    }

    private fun markerWindow(a5: RectI, nx: Float, ny: Float, side: Int): RectI {
        val cx = a5.l + (a5.w * nx).roundToInt()
        val cy = a5.t + (a5.h * ny).roundToInt()
        val half = side / 2
        return RectI(
            max(0, cx - half),
            max(0, cy - half),
            cx + half,
            cy + half
        )
    }

    private fun hasMarker(g: Gray, r: RectI): Boolean {
        val w = r.w
        val h = r.h
        if (w < 8 || h < 8) return false
        var sum = 0
        var minV = 255
        var maxV = 0
        var n = 0
        for (y in r.t until r.b) {
            if (y < 0 || y >= g.h) continue
            var i = y * g.w + r.l
            for (x in r.l until r.r) {
                if (x < 0 || x >= g.w) {
                    i++
                    continue
                }
                val v = g.px[i].toInt() and 0xFF
                sum += v
                if (v < minV) minV = v
                if (v > maxV) maxV = v
                n++
                i++
            }
        }
        if (n < 20) return false
        val mean = sum / n.toFloat()
        val contrast = mean - minV
        if (contrast < 14 && (maxV - minV) < 28) return false

        val thr = min(mean * 0.88f, mean - 12f)
        var dark = 0
        var sx = 0
        var sy = 0
        var minX = r.r
        var maxX = r.l
        var minY = r.b
        var maxY = r.t
        for (y in r.t until r.b) {
            if (y < 0 || y >= g.h) continue
            var i = y * g.w + r.l
            for (x in r.l until r.r) {
                if (x in 0 until g.w) {
                    val v = g.px[i].toInt() and 0xFF
                    if (v < thr) {
                        dark++
                        sx += x
                        sy += y
                        if (x < minX) minX = x
                        if (x > maxX) maxX = x
                        if (y < minY) minY = y
                        if (y > maxY) maxY = y
                    }
                }
                i++
            }
        }
        val frac = dark / n.toFloat()
        if (dark < 8) return false
        if (frac < 0.012f || frac > 0.82f) return false
        val bw = (maxX - minX + 1).toFloat()
        val bh = (maxY - minY + 1).toFloat()
        if (bw < 2 || bh < 2) return false
        val ar = bw / bh
        if (ar < 0.22f || ar > 4.6f) return false
        return true
    }

    private fun paperFill(g: Gray, r: RectI): Float {
        var bright = 0
        var n = 0
        val step = 2
        for (y in r.t until r.b step step) {
            var i = y * g.w + r.l
            for (x in r.l until r.r step step) {
                val v = g.px[i].toInt() and 0xFF
                if (v > 118) bright++
                n++
                i += step
            }
        }
        return if (n == 0) 0f else bright / n.toFloat()
    }

    private fun mean(g: Gray, r: RectI): Float {
        var sum = 0L
        var n = 0
        val step = 2
        for (y in r.t until r.b step step) {
            var i = y * g.w + r.l
            for (x in r.l until r.r step step) {
                sum += g.px[i].toInt() and 0xFF
                n++
                i += step
            }
        }
        return if (n == 0) 0f else sum / n.toFloat()
    }

    private fun sharpnessScore(g: Gray, r: RectI): Float {
        var acc = 0.0
        var n = 0
        val step = 2
        for (y in (r.t + 1) until (r.b - 1) step step) {
            for (x in (r.l + 1) until (r.r - 1) step step) {
                val c = g.at(x, y)
                val lap = 4 * c - g.at(x - 1, y) - g.at(x + 1, y) - g.at(x, y - 1) - g.at(x, y + 1)
                acc += lap * lap
                n++
            }
        }
        val variance = if (n == 0) 0.0 else acc / n
        return (sqrt(variance) / 28.0).toFloat().coerceIn(0f, 1f)
    }

    private fun downscaleUpright(image: ImageProxy, maxSide: Int): Gray? {
        val yPlane = image.planes.getOrNull(0) ?: return null
        val buf = yPlane.buffer
        val rowStride = yPlane.rowStride
        val pixelStride = yPlane.pixelStride
        val w = image.width
        val h = image.height
        val rot = image.imageInfo.rotationDegrees
        val scale = maxSide / max(w, h).toFloat()
        val nw = max(1, (w * scale).roundToInt())
        val nh = max(1, (h * scale).roundToInt())
        val src = ByteArray(nw * nh)
        val pos = buf.position()
        for (j in 0 until nh) {
            val sy = min(h - 1, (j / scale).toInt())
            for (i in 0 until nw) {
                val sx = min(w - 1, (i / scale).toInt())
                val idx = sy * rowStride + sx * pixelStride
                src[j * nw + i] = buf.get(idx)
            }
        }
        buf.position(pos)
        return rotate(Gray(src, nw, nh), rot)
    }

    private fun rotate(src: Gray, deg: Int): Gray {
        val d = ((deg % 360) + 360) % 360
        if (d == 0) return src
        return when (d) {
            90 -> {
                val out = ByteArray(src.w * src.h)
                for (y in 0 until src.h) {
                    for (x in 0 until src.w) {
                        out[x * src.h + (src.h - 1 - y)] = src.px[y * src.w + x]
                    }
                }
                Gray(out, src.h, src.w)
            }
            180 -> {
                val out = ByteArray(src.w * src.h)
                val n = src.px.size
                for (i in 0 until n) out[n - 1 - i] = src.px[i]
                Gray(out, src.w, src.h)
            }
            270 -> {
                val out = ByteArray(src.w * src.h)
                for (y in 0 until src.h) {
                    for (x in 0 until src.w) {
                        out[(src.w - 1 - x) * src.h + y] = src.px[y * src.w + x]
                    }
                }
                Gray(out, src.h, src.w)
            }
            else -> src
        }
    }

    private data class Gray(val px: ByteArray, val w: Int, val h: Int) {
        fun at(x: Int, y: Int): Int = px[y * w + x].toInt() and 0xFF
    }

    private data class RectI(val l: Int, val t: Int, val r: Int, val b: Int) {
        val w: Int get() = (r - l).coerceAtLeast(0)
        val h: Int get() = (b - t).coerceAtLeast(0)
    }
}
