package com.lectoraomr.camera

import android.app.Application
import com.lectoraomr.camera.data.LotRepository

class OmrCameraApp : Application() {
    lateinit var repo: LotRepository
        private set

    override fun onCreate() {
        super.onCreate()
        repo = LotRepository(this)
    }
}
