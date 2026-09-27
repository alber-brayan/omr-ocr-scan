package com.lectoraomr.camera.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.Typography
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

val Ink = Color(0xFF050816)
val InkLift = Color(0xFF0D162A)
val InkHigh = Color(0xFF17243B)
val InkSoft = Color(0xFF20304B)
val Paper = Color(0xFFF8FAFC)
val Mute = Color(0xFF93A4BC)
val Line = Color(0xFF243653)
val Accent = Color(0xFF5EEAD4)
val AccentDim = Color(0xFF103C3C)
val ElectricBlue = Color(0xFF38BDF8)
val ElectricViolet = Color(0xFF8B5CF6)
val Danger = Color(0xFFFB7185)
val Warn = Color(0xFFFBBF24)
val Sheet = Color(0xFFF8FAFC)

private val Colors = darkColorScheme(
    primary = Accent,
    onPrimary = Ink,
    secondary = ElectricBlue,
    tertiary = ElectricViolet,
    background = Ink,
    onBackground = Paper,
    surface = InkLift,
    onSurface = Paper,
    surfaceVariant = InkHigh,
    onSurfaceVariant = Mute,
    outline = Line,
    error = Danger
)

private val Type = Typography(
    displaySmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 30.sp,
        lineHeight = 34.sp,
        letterSpacing = (-1.1).sp,
        color = Paper
    ),
    headlineMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 24.sp,
        lineHeight = 29.sp,
        letterSpacing = (-0.6).sp
    ),
    titleLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 20.sp,
        lineHeight = 25.sp,
        letterSpacing = (-0.3).sp
    ),
    titleMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 16.sp,
        lineHeight = 21.sp
    ),
    bodyLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Normal,
        fontSize = 16.sp,
        lineHeight = 24.sp
    ),
    bodyMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        lineHeight = 20.sp,
        color = Mute
    ),
    labelLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 14.sp,
        letterSpacing = 0.2.sp
    ),
    labelSmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 10.sp,
        letterSpacing = 1.5.sp
    )
)

@Composable
fun LectoraTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = Colors,
        typography = Type,
        content = content
    )
}
