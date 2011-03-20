window.tweak_content=function() {
    var anchor=location.hash;
    if (anchor) {
        $(anchor).addClass('hilite').focus();
    }
    $('a:not(.internal-link)').attr('target','_blank');
}
$(function() {
    $.manageAjax.create('flocks',{queue:true}); 
    $('.flashes li').prepend($('<button/>').text('X').attr('href','#').click(function() {
        $(this).parent().slideUp(1000).remove(); return false;})).css('opacity',.9);
    window.tweak_content();
    $('.focusme:first').focus();
    if (window.SCROLLTO!=undefined && window.SCROLLTO) {
     	$('html,body').animate({scrollTop: $("#"+window.SCROLLTO).offset().top-60},'slow');
    }
});

window.populate_from_feed=function(ul,data) {
    for (e in data['entries']) { 
        if (e>=window.MAX_FEED_ENTRIES) { break; }
        entry=data['entries'][e];
        feed_dir=entry['feed_rtl']?'rtl':'ltr';
        var item_header=$('<div/>').addClass('toggler-label').addClass(feed_dir);
        item_header.append($('<div/>').addClass('item-time').text(entry['friendly_time']));
        item_header.append($('<span/>').addClass('feed-reference').text(entry['feed_title']));
        item_header.append(window.BUTTON_HTML[entry['feed_url']]);
        item_header.append($('<a/>').addClass('entry-title').attr(
            'href',entry['link']).html(entry['title']));
        var toggler = $('<input/>').addClass('toggler').attr('type','checkbox');
        if (window.EXPAND_ALL_ENTRIES) {toggler.attr('checked','checked');}
        var li=$('<li/>').attr('id',entry['id']).addClass('feed-entry').append(item_header).append(toggler);
        li.append($('<div/>').addClass('entry-description').addClass(feed_dir).html(entry['description']));
        li.data('modified',entry['modified']);
        var sameold=ul.find('#'+li.attr('id'));
        if (sameold.length) {
            // if it's hard to find out whether a checkbox is checked, might as well take the whole element :)
            li.find('input.toggler').replaceWith(sameold.find('input.toggler'));
            sameold.replaceWith(li);
        } else {
            var older=ul.find('li').filter(function() {
                return $(this).data('modified')<li.data('modified');
            });
            if (older.length) {
               	older.eq(0).before(li); 
            } else {
                ul.append(li);
            }
        };
        ul.find('li:gt('+window.MAX_PAGE_ENTRIES+')').remove();
    }
}

window.fetch_from_feed=function(ul_id,feed_title,feed_url) {
    var ul=$('#'+ul_id);
    var loading=$('<li/>').addClass('fetching-ajax').html(AJAX_LOADER_HTML).append(feed_title).data('modified','');
    $('#loading-list').append(loading);
    $.manageAjax.add('flocks',{
        url:window.AJAX_FEED_URL,
        data:{url:feed_url},
        ul:ul,
        refresh:"window.fetch_from_feed('"+ul_id+"','"+feed_title+"','"+feed_url+"')",
        refresh_seconds:1000*window.FEED_REFRESH_SECONDS,
        loading:loading,
        success:function(data,textStatus,xhr,options){
            options['loading'].slideUp(500).remove();
            populate_from_feed(options['ul'],data);
            window.tweak_content();
            setTimeout(options['refresh'],options['refresh_seconds']);
        },
        error:function(data,textStatus,xhr,options){
            options['loading'].find('img').replaceWith('Failed! ');
            options['loading'].prependTo($('#loading-list')).addClass(
                'hilite').click(function() {$(this).slideUp(1000).remove();});
            setTimeout(options['refresh'],options['refresh_seconds']);
        },
        abort:function(data,textStatus,xhr,options){
            options['loading'].find('img').replaceWith('Aborted! ');
            options['loading'].prependTo($('#loading-list')).addClass(
                'hilite').click(function() {$(this).slideUp(1000).remove();});
            setTimeout(options['refresh'],options['refresh_seconds']);
        }
    });
}
window.abort_all_fetches = function() {
    $.manageAjax.clear('flocks');
    $('.fetching-ajax').slideUp(500).remove();
}

