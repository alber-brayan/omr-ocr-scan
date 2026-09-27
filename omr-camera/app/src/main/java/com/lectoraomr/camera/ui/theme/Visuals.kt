package com.lectoraomr.camera.ui.theme

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

val AppGradient = Brush.verticalGradient(
    listOf(Color(0xFF050816), Color(0xFF081123), Color(0xFF06101E))
)

val PanelGradient = Brush.linearGradient(
    colors = listOf(Color(0xF217263D), Color(0xF20B1325)),
    start = Offset.Zero,
    end = Offset(950f, 760f)
)

val AccentGradient = Brush.linearGradient(
    colors = listOf(Color(0xFF99F6E4), Accent, ElectricBlue),
    start = Offset.Zero,
    end = Offset(800f, 350f)
)

@Composable
fun AppBackdrop(
    modifier: Modifier = Modifier,
    content: @Composable BoxScope.() -> Unit
) {
    Box(modifier.background(AppGradient)) {
        Canvas(Modifier.fillMaxSize()) {
            drawCircle(
                brush = Brush.radialGradient(
                    listOf(ElectricBlue.copy(alpha = 0.14f), Color.Transparent)
                ),
                radius = size.minDimension * 0.72f,
                center = Offset(size.width * 0.08f, size.height * 0.03f)
            )
            drawCircle(
                brush = Brush.radialGradient(
                    listOf(ElectricViolet.copy(alpha = 0.12f), Color.Transparent)
                ),
                radius = size.minDimension * 0.66f,
                center = Offset(size.width * 0.98f, size.height * 0.2f)
            )
            val step = 46.dp.toPx()
            var x = 0f
            while (x < size.width) {
                drawLine(Line.copy(alpha = 0.13f), Offset(x, 0f), Offset(x, size.height), 0.7f)
                x += step
            }
            var y = 0f
            while (y < size.height) {
                drawLine(Line.copy(alpha = 0.13f), Offset(0f, y), Offset(size.width, y), 0.7f)
                y += step
            }
        }
        content()
    }
}

fun Modifier.proPanel(
    radius: Dp = 22.dp,
    elevation: Dp = 18.dp,
    borderColor: Color = Line.copy(alpha = 0.68f),
    brush: Brush = PanelGradient
): Modifier {
    val shape: Shape = RoundedCornerShape(radius)
    return this
        .shadow(
            elevation = elevation,
            shape = shape,
            ambientColor = Color.Black.copy(alpha = 0.42f),
            spotColor = Color.Black.copy(alpha = 0.6f)
        )
        .clip(shape)
        .background(brush)
        .border(1.dp, borderColor, shape)
}
