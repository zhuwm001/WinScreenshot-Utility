; 我爱截图 —— 安装程序简体中文语言文件（精简版，未列出的条目回退到默认英文）

[LangOptions]
LanguageName=简体中文
LanguageID=$0804
LanguageCodePage=936
DialogFontName=Microsoft YaHei UI
DialogFontSize=9
WelcomeFontName=Microsoft YaHei UI
WelcomeFontSize=12
TitleFontName=Microsoft YaHei UI
TitleFontSize=29
CopyrightFontName=Microsoft YaHei UI
CopyrightFontSize=8

[Messages]

; *** 应用标题
SetupAppTitle=安装程序
SetupWindowTitle=安装 - %1
UninstallAppTitle=卸载
UninstallAppFullTitle=卸载 %1

; *** 通用
InformationTitle=提示
ConfirmTitle=确认
ErrorTitle=错误

; *** 启动错误
SetupFileMissing=安装目录缺少文件 %1。请修正该问题或重新获取安装程序。
SetupFileCorrupt=安装文件已损坏，请重新获取安装程序。
SetupAlreadyRunning=安装程序已经在运行。
WindowsVersionNotSupported=本程序不支持当前 Windows 版本。
AdminPrivilegesRequired=安装本程序需要管理员权限。
SetupAppRunningError=安装程序检测到 %1 正在运行。%n%n请先关闭它，然后点击“确定”继续，或点击“取消”退出。
UninstallAppRunningError=卸载程序检测到 %1 正在运行。%n%n请先关闭它，然后点击“确定”继续，或点击“取消”退出。

; *** 退出
ExitSetupTitle=退出安装
ExitSetupMessage=安装尚未完成。现在退出将不会安装本程序。%n%n之后可以重新运行安装程序完成安装。%n%n确定退出吗？
ButtonBack=< 上一步(&B)
ButtonNext=下一步(&N) >
ButtonInstall=安装(&I)
ButtonOK=确定
ButtonCancel=取消
ButtonYes=是(&Y)
ButtonYesToAll=全部是(&A)
ButtonNo=否(&N)
ButtonNoToAll=全部否(&O)
ButtonFinish=完成(&F)
ButtonBrowse=浏览(&B)...
ButtonWizardBrowse=浏览(&R)...
ButtonNewFolder=新建文件夹(&M)

; *** 选择语言
SelectLanguageTitle=选择安装语言
SelectLanguageLabel=选择安装过程中使用的语言。

; *** 通用向导文字
ClickNext=点击“下一步”继续，或点击“取消”退出安装。
BrowseDialogTitle=选择文件夹
BrowseDialogLabel=在下面的列表中选择一个文件夹，然后点击“确定”。
NewFolderName=新建文件夹

; *** 欢迎页
WelcomeLabel1=欢迎使用 [name] 安装向导
WelcomeLabel2=本向导将在您的电脑上安装 [name/ver]。%n%n建议在继续之前关闭其他正在运行的程序。

; *** 许可协议
WizardLicense=许可协议
LicenseLabel=继续之前请阅读以下重要信息。
LicenseLabel3=请阅读以下许可协议。您必须接受协议条款才能继续安装。
LicenseAccepted=我接受协议(&A)
LicenseNotAccepted=我不接受协议(&D)

; *** 信息页
WizardInfoBefore=信息
InfoBeforeLabel=继续之前请阅读以下重要信息。
InfoBeforeClickLabel=准备好继续时，请点击“下一步”。
WizardInfoAfter=信息
InfoAfterLabel=继续之前请阅读以下重要信息。
InfoAfterClickLabel=准备好继续时，请点击“下一步”。

; *** 选择目标位置
WizardSelectDir=选择目标位置
SelectDirDesc=[name] 应该安装到哪里？
SelectDirLabel3=安装程序将把 [name] 安装到以下文件夹。
SelectDirBrowseLabel=点击“下一步”继续。如果想选择其他文件夹，请点击“浏览”。
DiskSpaceGBLabel=至少需要 [gb] GB 可用磁盘空间。
DiskSpaceMBLabel=至少需要 [mb] MB 可用磁盘空间。
CannotInstallToNetworkDrive=安装程序无法安装到网络驱动器。
CannotInstallToUNCPath=安装程序无法安装到 UNC 路径。
InvalidPath=请输入带盘符的完整路径，例如：%n%nC:\APP%n%n或 UNC 路径：%n%n\\server\share
InvalidDrive=所选驱动器或 UNC 共享不存在或无法访问，请重新选择。
DiskSpaceWarningTitle=磁盘空间不足
DiskSpaceWarning=安装至少需要 %1 KB 可用空间，但所选驱动器仅有 %2 KB。%n%n仍要继续吗？
DirNameTooLong=文件夹名或路径过长。
InvalidDirName=文件夹名无效。
BadDirName32=文件夹名不能包含下列字符：%n%n%1
DirExistsTitle=文件夹已存在
DirExists=文件夹：%n%n%1%n%n已经存在。要安装到该文件夹吗？
DirDoesntExistTitle=文件夹不存在
DirDoesntExist=文件夹：%n%n%1%n%n不存在。要创建该文件夹吗？

; *** 选择组件
WizardSelectComponents=选择组件
SelectComponentsDesc=要安装哪些组件？
SelectComponentsLabel2=选择要安装的组件，取消勾选不需要的组件，然后点击“下一步”。
FullInstallation=全部安装
CompactInstallation=紧凑安装
CustomInstallation=自定义安装

; *** 附加任务
WizardSelectTasks=选择附加任务
SelectTasksDesc=要执行哪些附加任务？
SelectTasksLabel2=选择安装 [name] 时要执行的附加任务，然后点击“下一步”。

; *** 开始菜单
WizardSelectProgramGroup=选择开始菜单文件夹
SelectStartMenuFolderDesc=安装程序应该把程序快捷方式放在哪里？
SelectStartMenuFolderLabel3=安装程序将在以下开始菜单文件夹中创建快捷方式。
SelectStartMenuFolderBrowseLabel=点击“下一步”继续。如果想选择其他文件夹，请点击“浏览”。
MustEnterGroupName=请输入文件夹名。
NoProgramGroupCheck2=不创建开始菜单文件夹(&D)

; *** 准备安装
WizardReady=准备安装
ReadyLabel1=安装程序已准备好在您的电脑上安装 [name]。
ReadyLabel2a=点击“安装”开始安装，或点击“上一步”查看或更改设置。
ReadyLabel2b=点击“安装”开始安装。
ReadyMemoDir=目标位置：
ReadyMemoType=安装类型：
ReadyMemoComponents=已选组件：
ReadyMemoGroup=开始菜单文件夹：
ReadyMemoTasks=附加任务：

; *** 安装中
WizardPreparing=正在准备安装
PreparingDesc=安装程序正在准备安装 [name]。
CannotContinue=安装无法继续，请点击“取消”退出。
WizardInstalling=正在安装
InstallingLabel=正在您的电脑上安装 [name]，请稍候。
StatusCreateDirs=正在创建目录...
StatusExtractFiles=正在解压文件...
StatusCreateIcons=正在创建快捷方式...
StatusCreateRegistryEntries=正在写入注册表...
StatusSavingUninstall=正在保存卸载信息...
StatusRunProgram=正在完成安装...
StatusRollback=正在回滚更改...

; *** 完成
FinishedHeadingLabel=[name] 安装向导完成
FinishedLabelNoIcons=[name] 已安装到您的电脑上。
FinishedLabel=[name] 已安装到您的电脑上，可通过快捷方式启动。
ClickFinish=点击“完成”退出安装向导。
RunEntryExec=运行 %1

; *** 卸载
UninstallNotFound=文件“%1”不存在，无法卸载。
UninstallOpenError=无法打开文件“%1”，无法卸载。
UninstallUnsupportedVer=卸载日志“%1”的格式不被此版本识别，无法卸载。
UninstallUnknownEntry=卸载日志中出现未知条目（%1）。
ConfirmUninstall=确定要完全移除 %1 及其所有组件吗？
UninstallOnlyOnWin64=此安装只能在 64 位 Windows 上卸载。
OnlyAdminCanUninstall=只有管理员权限的用户才能卸载此安装。
UninstallStatusLabel=正在从您的电脑上移除 %1，请稍候。
UninstalledAll=%1 已成功从您的电脑上移除。
UninstalledMost=%1 卸载完成。%n%n部分元素无法移除，可以手动删除。
UninstalledAndNeedsRestart=要完成 %1 的卸载，需要重启电脑。%n%n现在重启吗？
UninstallDataCorrupted=“%1”文件已损坏，无法卸载。
WizardUninstalling=卸载状态
StatusUninstalling=正在卸载 %1...
ConfirmDeleteSharedFileTitle=删除共享文件？
SharedFileNameLabel=文件名：
SharedFileLocationLabel=位置：

; *** 自定义
[CustomMessages]
NameAndVersion=%1 版本 %2
AdditionalIcons=附加快捷方式：
CreateDesktopIcon=创建桌面快捷方式(&D)
UninstallProgram=卸载 %1
LaunchProgram=运行 %1
