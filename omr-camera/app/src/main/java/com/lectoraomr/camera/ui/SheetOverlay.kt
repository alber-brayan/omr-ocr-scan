package com.lectoraomr.camera.ui

import androidx.compose.foundation.Canvas
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.RoundRect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathFillType
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import com.lectoraomr.camera.camera.SheetQuality
import com.lectoraomr.camera.ui.theme.Accent
import com.lectoraomr.camera.ui.theme.Danger
import com.lectoraomr.camera.ui.theme.Ink
import com.lectoraomr.camera.ui.theme.Sheet
import com.lectoraomr.camera.ui.theme.Warn
import com.lectoraomr.camera.ui.theme.ElectricBlue

/** FIT_CENTER content box of the camera stream inside the view. */
fun fitContent(viewW: Float, viewH: Float, imageAspect: Float): Rect {
    val aspect = if (imageAspect > 0.05f) imageAspect else 3f / 4f
    val w: Float
    val h: Float
    if (viewW / viewH > aspect) {
        h = viewH
        w = h * aspect
    } else {
        w = viewW
        h = w / aspect
    }
    return Rect(Offset((viewW - w) / 2f, (viewH - h) / 2f), Size(w, h))
}

/** A5 148×210 inside a content rect (same math as the analyzer). */
fun a5Rect(content: Rect, margin: Float = 0.045f): Rect {
    val availW = content.width * (1f - 2f * margin)
    val availH = content.height * (1f - 2f * margin)
    val aspect = 148f / 210f
    val w: Float
    val h: Float
    if (availW / availH > aspect) {
        h = availH
        w = h * aspect
    } else {
        w = availW
        h = w / aspect
    }
    return Rect(
        offset = Offset(content.left + (content.width - w) / 2f, content.top + (content.height - h) / 2f),
        size = Size(w, h)
    )
}

@Composable
fun SheetOverlay(
    quality: SheetQuality,
    modifier: Modifier = Modifier
) {
    val scan = rememberInfiniteTransition(label = "scanLine")
    val scanProgress = scan.animateFloat(
        initialValue = 0.08f,
        targetValue = 0.92f,
        animationSpec = infiniteRepeatable(tween(1700), RepeatMode.Reverse),
        label = "scanProgress"
    ).value
    val strokeColor = when (quality.level) {
        SheetQuality.Level.Go -> Accent
        SheetQuality.Level.Almost -> Warn
        SheetQuality.Level.Stop -> Danger.copy(alpha = 0.85f)
    }
    Canvas(modifier) {
        val content = fitContent(size.width, size.height, quality.imageAspect)
        val frame = a5Rect(content)
        val dim = Path().apply {
            fillType = PathFillType.EvenOdd
            addRect(Rect(Offset.Zero, size))
            addRoundRect(RoundRect(frame, CornerRadius(10.dp.toPx(), 10.dp.toPx())))
        }
        drawPath(dim, Ink.copy(alpha = 0.42f))
        drawRoundRect(
            color = strokeColor,
            topLeft = frame.topLeft,
            size = frame.size,
            cornerRadius = CornerRadius(10.dp.toPx()),
            style = Stroke(width = 2.2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round)
        )

        // A moving scan beam gives immediate depth and makes alignment state legible.
        val beamY = frame.top + frame.height * scanProgress
        drawLine(
            color = if (quality.ready) Accent.copy(alpha = .9f) else ElectricBlue.copy(alpha = .42f),
            start = Offset(frame.left + 12.dp.toPx(), beamY),
            end = Offset(frame.right - 12.dp.toPx(), beamY),
            strokeWidth = if (quality.ready) 2.dp.toPx() else 1.dp.toPx(),
            cap = StrokeCap.Round
        )
        drawLine(
            color = (if (quality.ready) Accent else ElectricBlue).copy(alpha = .16f),
            start = Offset(frame.left + 20.dp.toPx(), beamY + 5.dp.toPx()),
            end = Offset(frame.right - 20.dp.toPx(), beamY + 5.dp.toPx()),
            strokeWidth = 7.dp.toPx(),
            cap = StrokeCap.Round
        )

        // Printed fiducials: 10 mm box, center 10 mm from page edge.
        val mark = frame.width * (10f / 148f)
        fun color(hit: Boolean) = if (hit) Accent else strokeColor.copy(alpha = 0.95f)
        fun at(nx: Float, ny: Float): Offset =
            Offset(frame.left + frame.width * nx - mark / 2f, frame.top + frame.height * ny - mark / 2f)

        val tl = at(0.0676f, 0.0476f)
        drawRoundRect(color(quality.corners.tl), tl, Size(mark, mark), CornerRadius(1.5.dp.toPx()))

        val tr = at(0.9324f, 0.0476f)
        drawRoundRect(
            color(quality.corners.tr),
            tr,
            Size(mark, mark),
            CornerRadius(1.5.dp.toPx()),
            style = Stroke(width = (mark * 0.22f).coerceAtLeast(2f))
        )

        val bl = at(0.0676f, 0.9524f)
        drawCircle(
            color(quality.corners.bl),
            radius = mark / 2f,
            center = Offset(bl.x + mark / 2f, bl.y + mark / 2f)
        )

        val br = at(0.9324f, 0.9524f)
        val thick = mark * 0.38f
        drawRoundRect(
            color(quality.corners.br),
            Offset(br.x + mark - thick, br.y),
            Size(thick, mark),
            CornerRadius(1.dp.toPx())
        )
        drawRoundRect(
            color(quality.corners.br),
            Offset(br.x, br.y + mark - thick),
            Size(mark, thick),
            CornerRadius(1.dp.toPx())
        )

        drawRoundRect(
            color = Sheet.copy(alpha = 0.03f),
            topLeft = frame.topLeft,
            size = frame.size,
            cornerRadius = CornerRadius(10.dp.toPx())
        )
    }
}
