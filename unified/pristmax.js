/**
 * PRISTMAX - 冰晶雪花动画
 */

class IceCanvas {
    constructor() {
        this.canvas = document.getElementById('fateCanvas');
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
        this.flakes = [];
        this.crystals = [];
        this.heroFade = 0;
        this.time = 0;
        this.init();
    }

    init() {
        this.resize();
        window.addEventListener('resize', () => this.resize());
        this.createFlakes();
        this.createCrystals();
        this.animate();
    }

    resize() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
    }

    createFlakes() {
        const count = Math.floor((this.canvas.width * this.canvas.height) / 18000);
        this.flakes = [];

        for (let i = 0; i < count; i++) {
            this.flakes.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height,
                size: Math.random() * 2.5 + 0.5,
                speed: Math.random() * 0.4 + 0.1,
                drift: (Math.random() - 0.5) * 0.3,
                opacity: Math.random() * 0.5 + 0.15,
                twinkle: Math.random() * Math.PI * 2
            });
        }
    }

    createCrystals() {
        // 六边形冰晶
        const count = 8;
        this.crystals = [];

        for (let i = 0; i < count; i++) {
            this.crystals.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height,
                size: Math.random() * 60 + 30,
                rotation: Math.random() * Math.PI * 2,
                rotationSpeed: (Math.random() - 0.5) * 0.002,
                opacity: Math.random() * 0.06 + 0.02
            });
        }
    }

    drawSnowflake(x, y, size, rotation, opacity) {
        const ctx = this.ctx;
        const arms = 6;

        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(rotation);
        ctx.globalAlpha = opacity;

        // 主干
        ctx.strokeStyle = `rgba(184, 226, 248, 1)`;
        ctx.lineWidth = 0.5;

        for (let i = 0; i < arms; i++) {
            const angle = (i / arms) * Math.PI * 2;
            const endX = Math.cos(angle) * size;
            const endY = Math.sin(angle) * size;

            ctx.beginPath();
            ctx.moveTo(0, 0);
            ctx.lineTo(endX, endY);
            ctx.stroke();

            // 分支
            const branchLength = size * 0.35;
            const branchAngle = angle + Math.PI / 6;

            ctx.beginPath();
            ctx.moveTo(endX * 0.6, endY * 0.6);
            ctx.lineTo(
                endX * 0.6 + Math.cos(branchAngle) * branchLength,
                endY * 0.6 + Math.sin(branchAngle) * branchLength
            );
            ctx.stroke();

            ctx.beginPath();
            ctx.moveTo(endX * 0.6, endY * 0.6);
            ctx.lineTo(
                endX * 0.6 + Math.cos(angle - Math.PI / 6) * branchLength,
                endY * 0.6 + Math.sin(angle - Math.PI / 6) * branchLength
            );
            ctx.stroke();
        }

        // 中心点
        ctx.beginPath();
        ctx.arc(0, 0, size * 0.08, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(200, 240, 255, 0.8)`;
        ctx.fill();

        ctx.restore();
    }

    drawHexagon(x, y, size, rotation, opacity) {
        const ctx = this.ctx;

        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(rotation);
        ctx.globalAlpha = opacity;

        ctx.beginPath();
        for (let i = 0; i < 6; i++) {
            const angle = (i / 6) * Math.PI * 2 - Math.PI / 2;
            const px = Math.cos(angle) * size;
            const py = Math.sin(angle) * size;
            if (i === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
        }
        ctx.closePath();
        ctx.strokeStyle = `rgba(168, 216, 234, 0.4)`;
        ctx.lineWidth = 0.5;
        ctx.stroke();

        ctx.restore();
    }

    animate() {
        const ctx = this.ctx;
        ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        this.time += 0.008;
        const fadeFactor = 1 - this.heroFade;

        // 绘制大冰晶背景
        this.crystals.forEach(crystal => {
            crystal.rotation += crystal.rotationSpeed;
            this.drawHexagon(
                crystal.x,
                crystal.y,
                crystal.size * fadeFactor,
                crystal.rotation,
                crystal.opacity * fadeFactor
            );
        });

        // 绘制雪花
        this.flakes.forEach(flake => {
            // 更新位置
            flake.y += flake.speed * fadeFactor;
            flake.x += flake.drift + Math.sin(this.time + flake.twinkle) * 0.2;

            // 环绕
            if (flake.y > this.canvas.height + 10) {
                flake.y = -10;
                flake.x = Math.random() * this.canvas.width;
            }
            if (flake.x < -10) flake.x = this.canvas.width + 10;
            if (flake.x > this.canvas.width + 10) flake.x = -10;

            // 闪烁
            const twinkle = Math.sin(this.time * 2 + flake.twinkle) * 0.3 + 0.7;
            const currentOpacity = flake.opacity * fadeFactor * twinkle;

            // 绘制雪花
            this.drawSnowflake(
                flake.x,
                flake.y,
                flake.size * fadeFactor,
                this.time + flake.twinkle,
                currentOpacity
            );
        });

        // 径向光晕
        const gradient = ctx.createRadialGradient(
            this.canvas.width * 0.5,
            this.canvas.height * 0.35,
            0,
            this.canvas.width * 0.5,
            this.canvas.height * 0.35,
            this.canvas.width * 0.5
        );

        gradient.addColorStop(0, `rgba(168, 216, 234, ${0.06 * fadeFactor})`);
        gradient.addColorStop(0.4, `rgba(184, 226, 248, ${0.03 * fadeFactor})`);
        gradient.addColorStop(1, 'transparent');

        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        this.animationId = requestAnimationFrame(() => this.animate());
    }

    setHeroFade(fade) {
        this.heroFade = fade;
    }
}

// 导出
window.IceCanvas = IceCanvas;
